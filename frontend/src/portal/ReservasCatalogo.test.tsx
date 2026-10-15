import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type FechasReservaPublica } from '../api/cliente';
import { ReservasCatalogo } from './ReservasCatalogo';

const propiedades: Parameters<typeof ReservasCatalogo>[0] = { id: 15, nombre: 'Altavoz activo Onda S12', cantidad: 3, hoy: '2027-11-01' };
const fechas: FechasReservaPublica = {
  equipment_id: 15,
  reservations: [
    { start_date: '2027-10-31', end_date: '2027-11-03' },
    { start_date: '2027-11-10', end_date: '2027-11-12' },
    { start_date: '2027-11-10', end_date: '2027-11-12' },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'obtenerFechasReservaPublica').mockResolvedValue(fechas);
});

describe("fechas de reservas del catálogo", () => {
  it("carga solo al solicitarlo y muestra los intervalos originales de recogida y devolución por separado, incluidos duplicados", async () => {
    render(<ReservasCatalogo {...propiedades} />);
    const usuario = userEvent.setup();
    const boton = screen.getByRole('button', { name: `Ver fechas de 3 reservas de ${propiedades.nombre}` });
    expect(boton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(api.obtenerFechasReservaPublica).not.toHaveBeenCalled();
    boton.focus();
    await usuario.keyboard('{Enter}');
    const lista = await screen.findByRole('list', { name: `Fechas reservadas de ${propiedades.nombre}` });
    expect(boton).toHaveFocus();
    expect(boton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('region')).toHaveAttribute('id', boton.getAttribute('aria-controls'));
    expect(within(lista).getAllByRole('listitem')).toHaveLength(3);
    expect(within(lista).getByText('31/10/2027')).toHaveAttribute('datetime', '2027-10-31');
    expect(within(lista).getByText('03/11/2027')).toHaveAttribute('datetime', '2027-11-03');
    expect(within(lista).getAllByText('10/11/2027')).toHaveLength(2);
    expect(within(lista).getAllByText('12/11/2027')).toHaveLength(2);
    expect(screen.getByText('El día de devolución no se incluye en el alquiler.')).toBeInTheDocument();
    expect(api.obtenerFechasReservaPublica).toHaveBeenCalledExactlyOnceWith(15, expect.any(AbortSignal));
  });

  it("permite consultar un recuento vacío y gestiona reservas canceladas desde la carga del catálogo", async () => {
    vi.mocked(api.obtenerFechasReservaPublica).mockResolvedValue({ equipment_id: 15, reservations: [] });
    render(<ReservasCatalogo {...propiedades} cantidad={0} />);
    const usuario = userEvent.setup();
    await usuario.click(screen.getByRole('button', { name: `Ver fechas de 0 reservas de ${propiedades.nombre}` }));
    expect(await screen.findByText('No hay reservas en curso ni próximas.')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it("actualiza el recuento mostrado con fechas recientes sin conservar un total desactualizado", async () => {
    vi.mocked(api.obtenerFechasReservaPublica).mockResolvedValue({ equipment_id: 15, reservations: [fechas.reservations[0]!] });
    render(<ReservasCatalogo {...propiedades} />);
    const usuario = userEvent.setup();
    await usuario.click(screen.getByRole('button'));
    expect(await screen.findByRole('button', { name: `Ocultar fechas de 1 reserva de ${propiedades.nombre}` })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button'));
    expect(screen.getByRole('button', { name: `Ver fechas de 1 reserva de ${propiedades.nombre}` })).toBeInTheDocument();
  });

  it("ofrece reintentar tras una lectura fallida y conserva el foco para cerrar con Escape", async () => {
    vi.mocked(api.obtenerFechasReservaPublica).mockRejectedValueOnce(new Error('No se pudieron cargar las fechas.'));
    render(<ReservasCatalogo {...propiedades} />);
    const usuario = userEvent.setup();
    const activador = screen.getByRole('button');
    await usuario.click(activador);
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron cargar las fechas.');
    await usuario.click(screen.getByRole('button', { name: 'Reintentar fechas' }));
    expect(await screen.findByRole('list')).toBeInTheDocument();
    expect(api.obtenerFechasReservaPublica).toHaveBeenCalledTimes(2);
    await usuario.keyboard('{Escape}');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(activador).toHaveFocus();
  });

  it("cancela al cerrar, consulta de nuevo al abrir e ignora una respuesta antigua tardía", async () => {
    let finalizar!: (valor: FechasReservaPublica) => void;
    vi.mocked(api.obtenerFechasReservaPublica).mockImplementationOnce(() => new Promise((resolver) => { finalizar = resolver; }))
      .mockResolvedValueOnce({ equipment_id: 15, reservations: [] });
    render(<ReservasCatalogo {...propiedades} />);
    const usuario = userEvent.setup();
    const activador = screen.getByRole('button');
    await usuario.click(activador);
    expect(screen.getByRole('status')).toHaveTextContent('Cargando fechas…');
    const senal = vi.mocked(api.obtenerFechasReservaPublica).mock.calls[0]![1]!;
    await usuario.keyboard('{Escape}');
    expect(senal.aborted).toBe(true);
    expect(activador).toHaveFocus();
    await usuario.keyboard(' ');
    await screen.findByText('No hay reservas en curso ni próximas.');
    await act(async () => { finalizar(fechas); });
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(screen.getByText('No hay reservas en curso ni próximas.')).toBeInTheDocument();
    expect(api.obtenerFechasReservaPublica).toHaveBeenCalledTimes(2);
  });

  it("actualiza un desplegable abierto al cambiar el día operativo de Madrid y cancela al desmontar", async () => {
    const { rerender: volverRenderizar, unmount: desmontar } = render(<ReservasCatalogo {...propiedades} />);
    await userEvent.setup().click(screen.getByRole('button'));
    await screen.findByRole('list');
    vi.mocked(api.obtenerFechasReservaPublica).mockResolvedValue({ equipment_id: 15, reservations: [] });
    volverRenderizar(<ReservasCatalogo {...propiedades} hoy="2027-11-02" />);
    await screen.findByText('No hay reservas en curso ni próximas.');
    await waitFor(() => expect(api.obtenerFechasReservaPublica).toHaveBeenCalledTimes(2));
    const senal = vi.mocked(api.obtenerFechasReservaPublica).mock.calls[1]![1]!;
    expect(senal.aborted).toBe(false);
    desmontar();
    expect(senal.aborted).toBe(true);
  });
});
