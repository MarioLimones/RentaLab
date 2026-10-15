import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi } from '../api/cliente';
import type { Disponibilidad, Equipo, Reserva } from '../api/cliente';
import PaginaDetalleReserva from './PaginaDetalleReserva';
import PaginaFormularioReserva from './PaginaFormularioReserva';
import PaginaReservas from './PaginaReservas';

const equipo: Equipo[] = [
  { id: 1, code: 'CAM-001', name: 'Cámara Aurora', category: 'Cámaras', description: '', active: true },
  { id: 2, code: 'AUD-001', name: 'Micrófono Brisa', category: 'Sonido', description: '', active: false },
];
const reserva: Reserva = {
  id: 8, equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
  start_date: '2026-11-10', end_date: '2026-11-12', status: 'confirmed', external_reference: 'DEMO-8',
};

function renderizarPagina(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/admin/reservas" element={<PaginaReservas />} />
        <Route path="/admin/reservas/nueva" element={<PaginaFormularioReserva />} />
        <Route path="/admin/reservas/:id" element={<PaginaDetalleReserva />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function rellenarReserva() {
  const usuario = userEvent.setup();
  await screen.findByRole('option', { name: /CAM-001/ });
  await usuario.selectOptions(screen.getByLabelText('Equipo'), '1');
  await usuario.type(screen.getByLabelText('Nombre del cliente'), 'Estudio Ficticio');
  await usuario.type(screen.getByLabelText('Correo del cliente'), 'estudio@example.test');
  fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-10' } });
  fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-12' } });
  await usuario.type(screen.getByLabelText(/Referencia externa/), 'DEMO-8');
  return usuario;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'listarEquipos').mockResolvedValue(equipo);
  vi.spyOn(api, 'listarReservas').mockResolvedValue([reserva]);
  vi.spyOn(api, 'obtenerReserva').mockResolvedValue(reserva);
  vi.spyOn(api, 'obtenerEquipo').mockResolvedValue(equipo[0]!);
  vi.spyOn(api, 'crearReserva').mockResolvedValue(reserva);
  vi.spyOn(api, 'cancelarReserva').mockResolvedValue({ ...reserva, status: 'cancelled' });
  vi.spyOn(api, 'obtenerDisponibilidadEquipo').mockResolvedValue({
    equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: true,
    reason: null, conflicting_reservation_ids: [],
  });
});

describe("formulario de reservas", () => {
  it("conserva todos los datos tras un conflicto, enfoca la explicación y reintenta correctamente", async () => {
    vi.mocked(api.crearReserva).mockRejectedValueOnce(new ErrorApi('El equipo ya tiene una reserva confirmada en ese intervalo.', 409));
    renderizarPagina('/admin/reservas/nueva');
    const usuario = await rellenarReserva();
    await usuario.click(screen.getByRole('button', { name: 'Crear reserva' }));
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('El equipo ya tiene una reserva confirmada');
    expect(alerta).toHaveFocus();
    expect(screen.getByLabelText('Equipo')).toHaveValue('1');
    expect(screen.getByLabelText('Nombre del cliente')).toHaveValue('Estudio Ficticio');
    expect(screen.getByLabelText('Correo del cliente')).toHaveValue('estudio@example.test');
    expect(screen.getByLabelText('Fecha de inicio')).toHaveValue('2026-11-10');
    expect(screen.getByLabelText('Fecha de fin')).toHaveValue('2026-11-12');
    expect(screen.getByLabelText(/Referencia externa/)).toHaveValue('DEMO-8');
    fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-11-12' } });
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-14' } });
    await usuario.click(screen.getByRole('button', { name: 'Crear reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #8' })).toBeInTheDocument();
    expect(api.crearReserva).toHaveBeenLastCalledWith({
      equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
      start_date: '2026-11-12', end_date: '2026-11-14', external_reference: 'DEMO-8',
    });
  });

  it("preselecciona el equipo, etiqueta unidades inactivas y envía las fechas sin convertir la zona horaria", async () => {
    renderizarPagina('/admin/reservas/nueva?equipment_id=2');
    const inactivo = await screen.findByRole('option', { name: /AUD-001.*inactivo/i });
    expect(inactivo).toBeEnabled();
    expect(screen.getByLabelText('Equipo')).toHaveValue('2');
    const usuario = await rellenarReserva();
    await usuario.clear(screen.getByLabelText(/Referencia externa/));
    await usuario.click(screen.getByRole('button', { name: 'Crear reserva' }));
    await waitFor(() => expect(api.crearReserva).toHaveBeenCalledWith({
      equipment_id: 1, customer_name: 'Estudio Ficticio', customer_email: 'estudio@example.test',
      start_date: '2026-11-10', end_date: '2026-11-12', external_reference: null,
    }));
  });

  it("muestra disponibilidad para el equipo y el intervalo exactos, la oculta si cambian las fechas y permite enviar un intervalo bloqueado", async () => {
    vi.mocked(api.obtenerDisponibilidadEquipo).mockResolvedValue({
      equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: false,
      reason: 'blocking_incident', conflicting_reservation_ids: [],
    });
    renderizarPagina('/admin/reservas/nueva');
    const usuario = await rellenarReserva();
    await usuario.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
    const resultado = await screen.findByRole('region', { name: 'Resultado de disponibilidad' });
    expect(resultado).toHaveTextContent('CAM-001');
    expect(resultado).toHaveTextContent('10/11/2026');
    expect(resultado).toHaveTextContent('12/11/2026');
    expect(resultado).toHaveTextContent(/incidencia bloqueante/i);
    expect(api.obtenerDisponibilidadEquipo).toHaveBeenCalledWith(1, { start_date: '2026-11-10', end_date: '2026-11-12' });
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-13' } });
    expect(screen.queryByRole('region', { name: 'Resultado de disponibilidad' })).not.toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Crear reserva' }));
    expect(api.crearReserva).toHaveBeenCalledTimes(1);
  });

  it("evita mostrar un resultado antiguo de disponibilidad que llega después de cambiar el intervalo consultado", async () => {
    let finalizar!: (valor: Disponibilidad) => void;
    vi.mocked(api.obtenerDisponibilidadEquipo).mockImplementation(() => new Promise((resolver) => { finalizar = resolver; }));
    renderizarPagina('/admin/reservas/nueva');
    const usuario = await rellenarReserva();
    await usuario.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-11-14' } });
    finalizar({ equipment_id: 1, start_date: '2026-11-10', end_date: '2026-11-12', available: true, reason: null, conflicting_reservation_ids: [] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Consultar disponibilidad' })).toBeEnabled());
    expect(screen.queryByRole('region', { name: 'Resultado de disponibilidad' })).not.toBeInTheDocument();
  });
});

describe("detalle de reserva", () => {
  it("exige confirmación explícita en la propia pantalla y muestra la cancelación sin borrar el historial", async () => {
    renderizarPagina('/admin/reservas/8');
    const usuario = userEvent.setup();
    await usuario.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    expect(api.cancelarReserva).not.toHaveBeenCalled();
    const confirmacion = screen.getByRole('group', { name: 'Confirmar cancelación' });
    expect(confirmacion).toHaveTextContent('historial');
    await usuario.click(within(confirmacion).getByRole('button', { name: 'Volver' }));
    expect(screen.queryByRole('group', { name: 'Confirmar cancelación' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelar reserva' })).toHaveFocus();
    await usuario.click(screen.getByRole('button', { name: 'Cancelar reserva' }));
    await usuario.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    await waitFor(() => expect(api.cancelarReserva).toHaveBeenCalledWith(8));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(screen.getByText('Estudio Ficticio')).toBeInTheDocument();
    expect(screen.getByText('DEMO-8')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancelar reserva' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Datos de la reserva' })).toHaveFocus();
  });
});

describe("filtros de la lista de reservas", () => {
  it("envía cliente, propietario y origen junto con los filtros existentes del servidor", async () => {
    renderizarPagina('/admin/reservas?customer_user_id=27');
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    expect(api.listarReservas).toHaveBeenCalledWith({ customer_user_id: 27 });
    expect(screen.getByLabelText('ID de cuenta')).toHaveValue('27');
    fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: '  estudio@example.test  ' } });
    fireEvent.change(screen.getByLabelText('Origen'), { target: { value: 'portal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listarReservas).toHaveBeenLastCalledWith({ customer: 'estudio@example.test', customer_user_id: 27, origin: 'portal' }));
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }));
    await waitFor(() => expect(api.listarReservas).toHaveBeenLastCalledWith({}));
  });

  it("identifica la cuenta propietaria y deja explícitas las importaciones y el historial sin propietario", async () => {
    vi.mocked(api.listarReservas).mockResolvedValue([
      { ...reserva, customer_user_id: 27, origin: 'portal' },
      { ...reserva, id: 9, customer_user_id: null, origin: 'csv' },
      { ...reserva, id: 10, customer_user_id: null, origin: 'legacy' },
    ]);
    renderizarPagina('/admin/reservas');
    await screen.findByRole('link', { name: 'Ver reserva #10' });
    expect(screen.getByText('Cuenta cliente #27')).toBeInTheDocument();
    expect(screen.getAllByText('Sin propietario de cuenta')).toHaveLength(2);
    expect(screen.getByText('Importación CSV', { selector: '.cell-subtitle' })).toBeInTheDocument();
    expect(screen.getByText('Histórico · origen no conocido', { selector: '.cell-subtitle' })).toBeInTheDocument();
  });

  it("carga las reservas actualizadas después de cancelar y volver a la lista", async () => {
    vi.mocked(api.cancelarReserva).mockImplementation(async () => {
      const cancelado = { ...reserva, status: 'cancelled' as const };
      vi.mocked(api.listarReservas).mockResolvedValue([cancelado]);
      return cancelado;
    });
    renderizarPagina('/admin/reservas');
    fireEvent.click(await screen.findByRole('link', { name: 'Ver reserva #8' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar reserva' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, cancelar reserva' }));
    await screen.findByText('Cancelada');
    fireEvent.click(screen.getByRole('link', { name: '← Reservas' }));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(api.listarReservas).toHaveBeenCalledTimes(2);
  });
  it("combina filtros del servidor y explica que el intervalo de fechas selecciona solapamientos", async () => {
    renderizarPagina('/admin/reservas');
    const usuario = userEvent.setup();
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    await usuario.selectOptions(screen.getByLabelText('Equipo'), '1');
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'confirmed');
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-11-11' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-11-20' } });
    await usuario.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    await waitFor(() => expect(api.listarReservas).toHaveBeenLastCalledWith({
      equipment_id: 1, status: 'confirmed', start_date: '2026-11-11', end_date: '2026-11-20',
    }));
    expect(screen.getByText(/solapan el intervalo/i)).toBeInTheDocument();
  });

  it("conserva un filtro incompleto de fechas en el formulario sin enviarlo al servidor", async () => {
    renderizarPagina('/admin/reservas');
    const usuario = userEvent.setup();
    await screen.findByRole('link', { name: 'Ver reserva #8' });
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-11-11' } });
    await usuario.click(screen.getByRole('button', { name: 'Aplicar filtros' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/ambas fechas/i);
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-11-11');
    expect(api.listarReservas).toHaveBeenCalledTimes(1);
  });
});
