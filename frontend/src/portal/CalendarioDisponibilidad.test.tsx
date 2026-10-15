import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi, type IntervaloFechas, type CalendarioDisponibilidadPublica } from '../api/cliente';
import { CalendarioDisponibilidad } from './CalendarioDisponibilidad';
import * as intervaloFechas from './intervaloFechas';
import { useCalendarioDisponibilidad } from './useCalendarioDisponibilidad';

function Calendario({ date: fecha = '2027-11-10', revision = 0 }: { date?: string; revision?: number }) {
  return <CalendarioDisponibilidad calendario={useCalendarioDisponibilidad(1, fecha, revision)} />;
}

function CalendarioInteractivo({ intervaloInicial = { start_date: '', end_date: '' }, disabled: deshabilitado = false, onChange: alCambiar }: { intervaloInicial?: IntervaloFechas; disabled?: boolean; onChange?: (intervalo: IntervaloFechas) => void }) {
  const [intervalo, establecerIntervalo] = useState(intervaloInicial);
  return <CalendarioDisponibilidad calendario={useCalendarioDisponibilidad(1, intervalo.start_date, 0, true)} intervalo={intervalo} deshabilitado={deshabilitado} onChange={(siguiente) => { establecerIntervalo(siguiente); alCambiar?.(siguiente); }} />;
}

const reservado = { start_date: '2027-11-10', end_date: '2027-11-12' };
const noviembre: CalendarioDisponibilidadPublica = { equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [reservado], can_book: true };

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(intervaloFechas, 'hoyEnMadrid').mockReturnValue('2027-11-01');
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, start_date: intervalo?.start_date ?? '2027-11-28', end_date: intervalo?.end_date ?? '2027-12-01', available: true, status: 'available' }));
  vi.spyOn(api, 'obtenerCalendarioDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ ...noviembre, equipment_id: id_equipo, ...intervalo }));
});

describe("calendario público de días ocupados", () => {
  it("marca solo días completos ocupados y deja disponible el fin excluido sin detalles privados de identidad", async () => {
    render(<Calendario />);
    expect(await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '11/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '12/11/2027: Disponible' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '09/11/2027: Disponible' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(7);
    expect(screen.getByText(/La devolución no cuenta como día de alquiler\./)).toBeInTheDocument();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01' }, expect.any(AbortSignal));
  });

  it("explica el bloqueo global de reservas sin presentar los días vacíos como reservables", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValue({ ...noviembre, can_book: false });
    render(<Calendario />);
    expect(await screen.findByText('Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '12/11/2027: No admite reservas' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
  });

  it("consulta otro mes con el teclado, incluidos cambios de año, y comienza la semana en lunes", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true }));
    const usuario = userEvent.setup();
    render(<Calendario date="2027-12-10" />);
    await screen.findByRole('table', { name: 'Ocupación de diciembre de 2027' });
    const siguiente = screen.getByRole('button', { name: 'Mes siguiente' });
    siguiente.focus();
    await usuario.keyboard('{Enter}');
    expect(await screen.findByRole('table', { name: 'Ocupación de enero de 2028' })).toBeInTheDocument();
    expect(siguiente).toHaveFocus();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenLastCalledWith(1, { start_date: '2028-01-01', end_date: '2028-02-01' }, expect.any(AbortSignal));
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('Lu');
    await usuario.click(screen.getByRole('button', { name: 'Mes anterior' }));
    expect(await screen.findByRole('table', { name: 'Ocupación de diciembre de 2027' })).toBeInTheDocument();
  });

  it("descarta resultados tardíos de un mes anterior después de cambiar las fechas seleccionadas", async () => {
    let finalizarAnterior!: (valor: CalendarioDisponibilidadPublica) => void;
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementationOnce(() => new Promise((resolver) => { finalizarAnterior = resolver; }))
      .mockResolvedValueOnce({ equipment_id: 1, start_date: '2028-02-01', end_date: '2028-03-01', occupied_ranges: [], can_book: true });
    const vista = render(<Calendario />);
    await waitFor(() => expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(1));
    vista.rerender(<Calendario date="2028-02-10" />);
    expect(await screen.findByRole('table', { name: 'Ocupación de febrero de 2028' })).toBeInTheDocument();
    await act(async () => { finalizarAnterior(noviembre); });
    expect(screen.getByRole('cell', { name: '29/02/2028: Disponible' })).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Ocupación de noviembre de 2027' })).not.toBeInTheDocument();
  });

  it("vuelve a consultar los intervalos confirmados después de guardar una reserva y conserva el mes seleccionado", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValueOnce({ ...noviembre, occupied_ranges: [] }).mockResolvedValue(noviembre);
    const vista = render(<Calendario />);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Disponible' })).toBeInTheDocument();
    vista.rerender(<Calendario revision={1} />);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(2);
  });

  it("permite recuperar un calendario fallido y evita presentar una ocupación antigua como actual", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockRejectedValueOnce(new ErrorApi('Sin conexión.', 0)).mockResolvedValue(noviembre);
    const usuario = userEvent.setup();
    render(<Calendario />);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Reintentar calendario' }));
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(2);
  });
});

describe("calendario interactivo de reservas", () => {
  it("bloquea un intervalo completo fragmentado aunque cada día tenga equipo disponible", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({
      equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true,
      unavailable_end_dates: intervalo.booking_start === '2027-11-15' ? ['2027-11-19', '2027-11-20'] : [],
    }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-15', end_date: '' }} onChange={cambiado} />);
    const regresoBloqueado = await screen.findByRole('button', { name: /20\/11\/2027: No disponible para esta devolución/ });
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01', booking_start: '2027-11-15' }, expect.any(AbortSignal));
    expect(regresoBloqueado).toHaveAttribute('aria-disabled', 'true');
    expect(regresoBloqueado.closest('td')).toHaveClass('calendar-day-blocked');
    await usuario.hover(regresoBloqueado);
    await usuario.click(regresoBloqueado);
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(cambiado).not.toHaveBeenCalled();
    const regresoPermitido = screen.getByRole('button', { name: '18/11/2027: Disponible' });
    await usuario.click(regresoPermitido);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '2027-11-18' });
  });

  it("actualiza las devoluciones permitidas tras cambiar la recogida dentro del mes y conserva el foco durante la consulta", async () => {
    let finalizar!: (valor: CalendarioDisponibilidadPublica) => void;
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValueOnce({ ...noviembre, occupied_ranges: [], unavailable_end_dates: [] })
      .mockImplementationOnce(() => new Promise((resolver) => { finalizar = resolver; }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    const recogida = await screen.findByRole('button', { name: '15/11/2027: Disponible' });
    recogida.focus();
    await usuario.keyboard('{Enter}');
    expect(recogida).toHaveFocus();
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
    const regresoPendiente = screen.getByRole('button', { name: /^20\/11\/2027: Disponible/ });
    expect(regresoPendiente).toHaveAttribute('aria-disabled', 'true');
    await usuario.click(regresoPendiente);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-15', end_date: '' });
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenLastCalledWith(1, { start_date: '2027-11-01', end_date: '2027-12-01', booking_start: '2027-11-15' }, expect.any(AbortSignal));
    await act(async () => { finalizar({ ...noviembre, occupied_ranges: [], unavailable_end_dates: ['2027-11-20'] }); });
    expect(screen.getByRole('button', { name: /20\/11\/2027: No disponible para esta devolución/ })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: '18/11/2027: Disponible' })).not.toHaveAttribute('aria-disabled', 'true');
  });

  it("previsualiza el intervalo de devolución disponible al pasar el puntero sin seleccionar fechas", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    const regresoBajoCursor = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    await usuario.hover(regresoBajoCursor);

    expect(screen.getByRole('button', { name: /^06\/11\/2027:/ }).closest('td')).toHaveClass('calendar-day-start');
    expect(screen.getByRole('button', { name: '07/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(screen.getByRole('button', { name: '08/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(regresoBajoCursor.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '05/11/2027: Disponible' }).closest('td')).not.toHaveClass('calendar-day-preview');
    expect(regresoBajoCursor).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '08/11/2027: Disponible' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(cambiado).not.toHaveBeenCalled();

    await usuario.unhover(regresoBajoCursor);
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("limpia la previsualización de intervalos bloqueados y permite el primer día ocupado como devolución excluida", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    await usuario.hover(await screen.findByRole('button', { name: '09/11/2027: Disponible' }));
    expect(vista.container.querySelector('.calendar-day-preview-end')).toBeInTheDocument();

    await usuario.hover(screen.getByRole('button', { name: /^13\/11\/2027:/ }));
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    await usuario.hover(screen.getByRole('button', { name: /^11\/11\/2027: Ocupado/ }));
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();

    const devolucionContigua = screen.getByRole('button', { name: '10/11/2027: Ocupado. Devolución posible' });
    await usuario.hover(devolucionContigua);
    expect(devolucionContigua.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '09/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(devolucionContigua).toHaveAttribute('aria-pressed', 'false');
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("previsualiza la fecha de devolución enfocada con el teclado antes de confirmarla con Enter", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    const recogida = await screen.findByRole('button', { name: /^06\/11\/2027:/ });
    act(() => recogida.focus());
    await usuario.keyboard('{ArrowRight}{ArrowRight}');
    const regresoEnfocado = screen.getByRole('button', { name: '08/11/2027: Disponible' });
    expect(regresoEnfocado).toHaveFocus();
    expect(regresoEnfocado.closest('td')).toHaveClass('calendar-day-preview-end');
    expect(screen.getByRole('button', { name: '07/11/2027: Disponible' }).closest('td')).toHaveClass('calendar-day-preview');
    expect(regresoEnfocado).toHaveAttribute('aria-pressed', 'false');
    expect(cambiado).not.toHaveBeenCalled();

    await usuario.keyboard('{Enter}');
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-06', end_date: '2027-11-08' });
    expect(screen.getByRole('button', { name: /^08\/11\/2027:/ })).toHaveAttribute('aria-pressed', 'true');
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
  });

  it("evita previsualizar días pasados o fechas mientras la confirmación deshabilita el calendario", async () => {
    vi.mocked(intervaloFechas.hoyEnMadrid).mockReturnValue('2027-11-05');
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    await usuario.hover(await screen.findByRole('button', { name: '04/11/2027: Fecha pasada' }));
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    vista.rerender(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} disabled onChange={cambiado} />);
    await usuario.hover(screen.getByRole('button', { name: '09/11/2027: Disponible' }));
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("evita previsualizar fechas cuando el equipo no admite reservas", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValue({ ...noviembre, can_book: false });
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    await usuario.hover(await screen.findByRole('button', { name: '09/11/2027: No admite reservas' }));
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("evita dejar una previsualización persistente tras utilizar un puntero táctil", async () => {
    const cambiado = vi.fn();
    const vista = render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-06', end_date: '' }} onChange={cambiado} />);
    const fechaDevolucion = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    fireEvent.pointerEnter(fechaDevolucion, { pointerType: 'touch', pointerId: 1 });
    expect(vista.container.querySelector('.calendar-day-preview, .calendar-day-preview-end')).not.toBeInTheDocument();
    expect(fechaDevolucion).toHaveAttribute('aria-pressed', 'false');
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("comienza por la recogida si se abre la devolución sin haber elegido fechas", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    await usuario.click(await screen.findByRole('button', { name: 'Fecha de devolución: Elegir día' }));
    await usuario.click(screen.getByRole('button', { name: '08/11/2027: Disponible' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it("muestra disponibilidad antes de seleccionar y elige inicio y devolución excluida en dos clics", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    const inicio = await screen.findByRole('button', { name: '08/11/2027: Disponible' });
    expect(screen.getByRole('button', { name: /^Fecha de inicio:/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Fecha de devolución:/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '10/11/2027: Ocupado' })).toHaveAttribute('aria-disabled', 'true');
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.click(inicio);
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '' });
    await usuario.click(screen.getByRole('button', { name: '09/11/2027: Disponible' }));
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-09' });
    expect(cambiado).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: /^Fecha de inicio:.*08\/11\/2027/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Fecha de devolución:.*09\/11\/2027/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cambiar fechas' })).toBeInTheDocument();
  });

  it("impide elegir un intervalo con días ocupados entre un inicio y una devolución disponibles", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    await usuario.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    const devolucionTrasOcupacion = screen.getByRole('button', { name: /^13\/11\/2027:/ });
    expect(devolucionTrasOcupacion).toHaveAttribute('aria-disabled', 'true');
    await usuario.click(devolucionTrasOcupacion);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it("permite devolver el día en que empieza la siguiente reserva porque ese día queda excluido", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    await usuario.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    const devolucionContigua = screen.getByRole('button', { name: '10/11/2027: Ocupado. Devolución posible' });
    expect(devolucionContigua).not.toHaveAttribute('aria-disabled', 'true');
    await usuario.click(devolucionContigua);
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: '2027-11-08', end_date: '2027-11-10' });
    expect(cambiado).toHaveBeenCalledTimes(2);
  });

  it("evita confundir una reserva recortada en el límite del mes con una devolución posible", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({
      equipment_id: id_equipo, ...intervalo, can_book: true,
      occupied_ranges: intervalo.start_date === '2027-11-01'
        ? [{ start_date: '2027-11-29', end_date: '2027-12-01' }]
        : [{ start_date: '2027-12-01', end_date: '2027-12-03' }],
    }));
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, start_date: intervalo?.start_date ?? '2027-11-28', end_date: intervalo?.end_date ?? '2027-12-01', available: false, status: 'unavailable' }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-28', end_date: '' }} onChange={cambiado} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await usuario.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const ocupacionesRecortadas = await screen.findByRole('button', { name: /^01\/12\/2027: Ocupado/ });
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-28', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(ocupacionesRecortadas).toHaveAttribute('aria-disabled', 'true');
    expect(ocupacionesRecortadas).not.toHaveAccessibleName(/Devolución posible/);
    const diaLibreTrasOcupacion = screen.getByRole('button', { name: /^04\/12\/2027: Disponible/ });
    expect(diaLibreTrasOcupacion).toHaveAttribute('aria-disabled', 'true');
    await usuario.click(ocupacionesRecortadas);
    await usuario.click(diaLibreTrasOcupacion);
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("permite devolver el primer día ocupado de un mes nuevo si todo el periodo anterior está libre", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({
      equipment_id: id_equipo, ...intervalo, can_book: true,
      occupied_ranges: intervalo.start_date === '2027-12-01' ? [{ start_date: '2027-12-01', end_date: '2027-12-03' }] : [],
    }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-28', end_date: '' }} onChange={cambiado} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await usuario.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const devolucionContigua = await screen.findByRole('button', { name: '01/12/2027: Ocupado. Devolución posible' });
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-28', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(devolucionContigua).not.toHaveAttribute('aria-disabled', 'true');
    await usuario.click(devolucionContigua);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-28', end_date: '2027-12-01' });
  });

  it("conserva la recogida original al comprobar disponibilidad fragmentada entre meses", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({
      equipment_id: id_equipo, ...intervalo, can_book: true, occupied_ranges: [],
      unavailable_end_dates: intervalo.start_date === '2027-12-01' ? ['2027-12-03'] : [],
    }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo intervaloInicial={{ start_date: '2027-11-28', end_date: '' }} onChange={cambiado} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await usuario.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    const regresoBloqueado = await screen.findByRole('button', { name: /03\/12\/2027: No disponible para esta devolución/ });
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenLastCalledWith(1, { start_date: '2027-12-01', end_date: '2028-01-01', booking_start: '2027-11-28' }, expect.any(AbortSignal));
    expect(regresoBloqueado).toHaveAttribute('aria-disabled', 'true');
    await usuario.click(regresoBloqueado);
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("permite corregir meses no válidos de la URL al editar las fechas seleccionadas", async () => {
    const consulta = new URLSearchParams('start_date=2027-99-10&end_date=2027-11-12');
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo intervaloInicial={{ start_date: consulta.get('start_date')!, end_date: consulta.get('end_date')! }} onChange={cambiado} />);
    await screen.findByRole('table', { name: 'Ocupación de noviembre de 2027' });
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/99/2027' }));
    expect(screen.getByRole('table', { name: 'Ocupación de noviembre de 2027' })).toBeInTheDocument();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, { start_date: '2027-11-01', end_date: '2027-12-01' }, expect.any(AbortSignal));
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: '08/11/2027: Disponible' }));
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-08', end_date: '' });
  });

  it("mantiene los días pasados accesibles con teclado aunque impide seleccionarlos", async () => {
    vi.mocked(intervaloFechas.hoyEnMadrid).mockReturnValue('2027-11-05');
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    const hoy = await screen.findByRole('button', { name: /^05\/11\/2027:/ });
    const pasado = screen.getByRole('button', { name: /^04\/11\/2027:/ });
    expect(pasado).toHaveAttribute('aria-disabled', 'true');
    expect(pasado).not.toBeDisabled();
    hoy.focus();
    await usuario.keyboard('{ArrowLeft}{Enter}');
    expect(pasado).toHaveFocus();
    await usuario.click(pasado);
    expect(cambiado).not.toHaveBeenCalled();
    await usuario.click(hoy);
    expect(cambiado).toHaveBeenCalledExactlyOnceWith({ start_date: '2027-11-05', end_date: '' });
  });

  it("mantiene los días ocupados accesibles con teclado sin seleccionarlos como inicio del alquiler", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    const antesOcupacion = await screen.findByRole('button', { name: '09/11/2027: Disponible' });
    const noDisponible = screen.getByRole('button', { name: '10/11/2027: Ocupado' });
    expect(noDisponible).not.toBeDisabled();
    antesOcupacion.focus();
    await usuario.keyboard('{ArrowRight}{Enter}');
    expect(noDisponible).toHaveFocus();
    expect(noDisponible).toHaveAttribute('aria-disabled', 'true');
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("bloquea la selección mientras confirma y cuando el producto no admite reservas", async () => {
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    const vista = render(<CalendarioInteractivo disabled onChange={cambiado} />);
    await usuario.click(await screen.findByRole('button', { name: '08/11/2027: Disponible' }));
    expect(cambiado).not.toHaveBeenCalled();
    vista.unmount();
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValue({ ...noviembre, can_book: false });
    render(<CalendarioInteractivo onChange={cambiado} />);
    const noDisponible = await screen.findByRole('button', { name: '08/11/2027: No admite reservas' });
    expect(noDisponible).toHaveAttribute('aria-disabled', 'true');
    await usuario.click(noDisponible);
    expect(cambiado).not.toHaveBeenCalled();
  });

  it("desplaza el foco del teclado entre meses y selecciona las fechas nuevas con Enter", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    const ultimoDiaNoviembre = await screen.findByRole('button', { name: '30/11/2027: Disponible' });
    ultimoDiaNoviembre.focus();
    await usuario.keyboard('{ArrowRight}');
    const inicioDiciembre = await screen.findByRole('button', { name: '01/12/2027: Disponible' });
    await waitFor(() => expect(inicioDiciembre).toHaveFocus());
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenLastCalledWith(1, { start_date: '2027-12-01', end_date: '2028-01-01' }, expect.any(AbortSignal));
    await usuario.keyboard('{Enter}{ArrowRight}{Enter}');
    expect(cambiado).toHaveBeenLastCalledWith({ start_date: '2027-12-01', end_date: '2027-12-02' });
    expect(cambiado).toHaveBeenCalledTimes(2);
  });

  it("admite extremos de semana, movimiento semanal y teclas de página sin cambiar el intervalo seleccionado", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo, occupied_ranges: [], can_book: true }));
    const cambiado = vi.fn();
    const usuario = userEvent.setup();
    render(<CalendarioInteractivo onChange={cambiado} />);
    (await screen.findByRole('button', { name: '17/11/2027: Disponible' })).focus();
    await usuario.keyboard('{Home}');
    expect(screen.getByRole('button', { name: '15/11/2027: Disponible' })).toHaveFocus();
    await usuario.keyboard('{End}');
    expect(screen.getByRole('button', { name: '21/11/2027: Disponible' })).toHaveFocus();
    await usuario.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: '28/11/2027: Disponible' })).toHaveFocus();
    await usuario.keyboard('{ArrowUp}{PageDown}');
    await waitFor(() => expect(screen.getByRole('button', { name: '21/12/2027: Disponible' })).toHaveFocus());
    await usuario.keyboard('{PageUp}');
    await waitFor(() => expect(screen.getByRole('button', { name: '21/11/2027: Disponible' })).toHaveFocus());
    expect(cambiado).not.toHaveBeenCalled();
  });
});
