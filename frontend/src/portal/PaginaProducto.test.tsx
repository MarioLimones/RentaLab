import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi, type SesionAutenticacion, type ReservaCliente, type DisponibilidadPublica, type EquipoPublico } from '../api/cliente';
import { ContextoAutenticacion, type EstadoAutenticacion } from '../autenticacion/contexto';
import { formatearFecha } from '../utilidades/fechas';
import { hoyEnMadrid } from './intervaloFechas';
import { PaginaProducto } from './PaginaProducto';
import { leerIntentoReserva, ambitoReserva } from './intentoReserva';

const equipo: EquipoPublico = {
  id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: 'Para entrevistas en estudio.',
  technical_specs: { Resolución: '4K UHD', Conexiones: 'HDMI y USB-C' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0,
};
const sesion: SesionAutenticacion = {
  authenticated: true, username: 'ana@example.test', expires_at: '2026-11-30T12:00:00Z', role: 'customer',
  user: { id: 4, name: 'Ana', email: 'ana@example.test', role: 'customer', active: true },
};
const intervalo = { start_date: '2027-11-10', end_date: '2027-11-12' };
const disponible: DisponibilidadPublica = { equipment_id: 1, ...intervalo, available: true, status: 'available' };

function Ubicacion() {
  const ubicacion = useLocation();
  return <p data-testid="location">{ubicacion.pathname}{ubicacion.search}</p>;
}

function renderizarProducto(usuario: SesionAutenticacion | null = sesion, ruta = '/equipos/1?start_date=2027-11-10&end_date=2027-11-12') {
  return render(<ContextoAutenticacion.Provider value={{ sesion: usuario, comprobando: false, errorComprobacion: null, caducado: false, iniciarSesion: vi.fn(), cerrarSesionUsuario: vi.fn(), comprobarSesion: vi.fn() }}><MemoryRouter initialEntries={[ruta]}><Ubicacion /><Routes><Route path="/equipos/:id" element={<PaginaProducto />} /><Route path="/acceso" element={<h1>Accede a tu cuenta</h1>} /></Routes></MemoryRouter></ContextoAutenticacion.Provider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.spyOn(api, 'obtenerEquipoPublico').mockResolvedValue(equipo);
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockImplementation(async (id_equipo, fechas) => ({ equipment_id: id_equipo, ...fechas, available: true, status: 'available' }));
  vi.spyOn(api, 'obtenerCalendarioDisponibilidadPublica').mockImplementation(async (id_equipo, fechas) => ({ equipment_id: id_equipo, ...fechas, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'crearMiReserva').mockImplementation(async (reserva) => ({ id: 42, ...reserva, status: 'confirmed' }));
});

describe("producto público y reserva explícita", () => {
  it("reintenta una confirmación incierta con la misma clave aunque el intervalo ya esté ocupado", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No hemos podido comprobar si se confirmó.');
    const key = vi.mocked(api.crearMiReserva).mock.calls[0]![1];
    expect(key).toMatch(/^[0-9a-f-]{36}$/i);
    vi.mocked(api.obtenerDisponibilidadPublica).mockResolvedValue({ ...disponible, available: false, status: 'unavailable' });
    await usuario.click(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.crearMiReserva).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...intervalo }, key);
  });

  it("restaura un intento incierto tras remontar y resolver tarde la sesión sin enviar automáticamente", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    const primero = renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.crearMiReserva).mock.calls[0]![1];
    primero.unmount();
    vi.mocked(api.obtenerDisponibilidadPublica).mockResolvedValue({ ...disponible, available: false, status: 'unavailable' });
    const valor: EstadoAutenticacion = { sesion: null as SesionAutenticacion | null, comprobando: true, errorComprobacion: null, caducado: false, iniciarSesion: vi.fn(), cerrarSesionUsuario: vi.fn(), comprobarSesion: vi.fn() };
    const children = <MemoryRouter initialEntries={['/equipos/1?start_date=2027-11-10&end_date=2027-11-12']}><Routes><Route path="/equipos/:id" element={<PaginaProducto />} /></Routes></MemoryRouter>;
    const segundo = render(<ContextoAutenticacion.Provider value={valor}>{children}</ContextoAutenticacion.Provider>);
    await screen.findByRole('heading', { name: equipo.name });
    segundo.rerender(<ContextoAutenticacion.Provider value={{ ...valor, sesion, comprobando: false }}>{children}</ContextoAutenticacion.Provider>);
    const reintento = await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    expect(reintento).toBeEnabled();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    await usuario.click(reintento);
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(api.crearMiReserva).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...intervalo }, key);
  });

  it("conserva una operación completada al recargar y renueva su clave solo para otra reserva explícita", async () => {
    const primero = renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    const key = vi.mocked(api.crearMiReserva).mock.calls[0]![1];
    primero.unmount();
    renderizarProducto();
    await screen.findByRole('region', { name: 'Reserva registrada' });
    expect(screen.queryByRole('button', { name: 'Confirmar reserva' })).not.toBeInTheDocument();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.crearMiReserva).mock.calls[1]![1]).not.toBe(key);
  });

  it("crea claves de operación distintas para otra cuenta y para fechas cambiadas deliberadamente", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    const primero = renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const primeraClave = vi.mocked(api.crearMiReserva).mock.calls[0]![1];
    primero.unmount();
    const segundo = renderizarProducto({ ...sesion, user: { ...sesion.user!, id: 9 } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.crearMiReserva).mock.calls[1]![1]).not.toBe(primeraClave);
    segundo.unmount();
    renderizarProducto();
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    await usuario.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await usuario.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.crearMiReserva).mock.calls[2]![1]).not.toBe(primeraClave);
    expect(leerIntentoReserva(ambitoReserva(4, { equipment_id: 1, ...intervalo }))?.key).toBe(primeraClave);
  });

  it("conserva la intención incierta original después de cambiar las fechas y recuperarlas", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.crearMiReserva).mock.calls[0]![1];
    await usuario.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await usuario.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Fecha de devolución: 14/11/2027' }));
    await usuario.click(await screen.findByRole('button', { name: '12/11/2027: Disponible' }));
    await usuario.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(api.crearMiReserva).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...intervalo }, key);
  });

  it("muestra el estado cancelado real devuelto por una repetición idempotente", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Lost response', 500))
      .mockResolvedValueOnce({ id: 42, equipment_id: 1, ...intervalo, status: 'cancelled' });
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await usuario.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(screen.queryByText('Tu reserva se ha confirmado.')).not.toBeInTheDocument();
  });

  it("conserva los filtros del catálogo al volver con fechas cambiadas del producto y rechaza destinos externos", async () => {
    const catalogo = '/catalogo?q=Aurora&category=C%C3%A1maras&available=1';
    const primero = renderizarProducto(sesion, `/equipos/1?start_date=2027-11-10&end_date=2027-11-12&catalogue=${encodeURIComponent(catalogo)}`);
    await screen.findByRole('heading', { name: equipo.name });
    const usuario = userEvent.setup();
    await usuario.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await usuario.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    const volver = new URL(screen.getByRole('link', { name: 'Volver al catálogo' }).getAttribute('href')!, 'https://rentalab.invalid');
    expect(Object.fromEntries(volver.searchParams)).toEqual({ start_date: intervalo.start_date, end_date: '2027-11-14', q: 'Aurora', category: 'Cámaras', available: '1' });
    primero.unmount();
    renderizarProducto(sesion, `/equipos/1?start_date=2027-11-10&end_date=2027-11-12&catalogue=${encodeURIComponent('https://evil.test')}`);
    expect(await screen.findByRole('link', { name: 'Volver al catálogo' })).toHaveAttribute('href', '/catalogo?start_date=2027-11-10&end_date=2027-11-12');
  });

  it("conserva equipo y fechas en el destino de acceso permitido sin crear una reserva", async () => {
    renderizarProducto(null);
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Acceder para reservar' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Acceder para reservar' }));
    await screen.findByRole('heading', { name: 'Accede a tu cuenta' });
    const destino = new URLSearchParams(screen.getByTestId('location').textContent?.split('?')[1]).get('next');
    expect(destino).toBe('/equipos/1?start_date=2027-11-10&end_date=2027-11-12');
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("exige pulsar después de volver con sesión y muestra referencia, estado y enlace de detalle", async () => {
    renderizarProducto();
    await screen.findByText('Disponible del 10/11/2027 al 12/11/2027.');
    expect(api.crearMiReserva).not.toHaveBeenCalled();
    const usuario = userEvent.setup();
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(screen.getByText('Confirmada')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/42');
    expect(api.crearMiReserva).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...intervalo }, expect.any(String));
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(2));
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(2);
  });

  it("confirma una reserva asignada a una unidad hermana manteniendo una única presentación pública del producto", async () => {
    vi.mocked(api.crearMiReserva).mockResolvedValue({ id: 43, equipment_id: 2, ...intervalo, status: 'confirmed' });
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #43' })).toHaveFocus();
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/43');
    expect(api.crearMiReserva).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...intervalo }, expect.any(String));
    expect(screen.queryByText(/unidades|equipo #2/i)).not.toBeInTheDocument();
  });

  it("inmoviliza las fechas seleccionadas mientras confirma e impide un segundo envío", async () => {
    let finalizar!: (reserva: ReservaCliente) => void;
    vi.mocked(api.crearMiReserva).mockImplementation(() => new Promise((resolver) => { finalizar = resolver; }));
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.dblClick(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '14/11/2027: Disponible' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirmando reserva…' })).toBeDisabled();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    await act(async () => { finalizar({ id: 42, equipment_id: 1, ...intervalo, status: 'confirmed' }); });
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
  });

  it("conserva las fechas y enfoca el conflicto, actualiza automáticamente el calendario y permite otras fechas", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('El equipo no está disponible.', 409));
    vi.mocked(api.obtenerDisponibilidadPublica).mockResolvedValueOnce(disponible).mockResolvedValue({ ...disponible, status: 'unavailable', available: false });
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValueOnce({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true })
      .mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [intervalo], can_book: true });
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('La disponibilidad ha cambiado');
    expect(alerta).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(2));
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Reserva #42' })).not.toBeInTheDocument();
    vi.mocked(api.obtenerDisponibilidadPublica).mockResolvedValue({ ...disponible, start_date: '2027-11-12', end_date: '2027-11-14', available: true, status: 'available' });
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' }));
    await usuario.click(screen.getByRole('button', { name: /^12\/11\/2027: Disponible/ }));
    await usuario.click(screen.getByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(2);
  });

  it("ignora un resultado antiguo de disponibilidad después de cambiar la fecha seleccionada", async () => {
    let resolverAnterior!: (valor: DisponibilidadPublica) => void;
    let resolverNuevo!: (valor: DisponibilidadPublica) => void;
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementationOnce(() => new Promise((resolver) => { resolverAnterior = resolver; })).mockImplementationOnce(() => new Promise((resolver) => { resolverNuevo = resolver; }));
    renderizarProducto();
    await screen.findByRole('heading', { name: equipo.name });
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(1));
    const usuario = userEvent.setup();
    await usuario.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await usuario.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(2));
    await act(async () => { resolverAnterior(disponible); });
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    await act(async () => { resolverNuevo({ equipment_id: 1, start_date: intervalo.start_date, end_date: '2027-11-14', available: false, status: 'unavailable' }); });
    expect(await screen.findByText('No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.')).toBeInTheDocument();
  });

  it("muestra la ocupación antes de elegir fechas y comprueba automáticamente la selección del calendario", async () => {
    const mes = hoyEnMadrid().slice(0, 7);
    const fechaMesSiguiente = new Date(`${mes}-01T12:00:00Z`);
    fechaMesSiguiente.setUTCMonth(fechaMesSiguiente.getUTCMonth() + 1);
    const mesSiguiente = fechaMesSiguiente.toISOString().slice(0, 7);
    const seleccionado = { start_date: `${mesSiguiente}-10`, end_date: `${mesSiguiente}-12` };
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, fechas) => ({
      equipment_id: id_equipo, ...fechas, occupied_ranges: [{ start_date: `${fechas.start_date.slice(0, 7)}-06`, end_date: `${fechas.start_date.slice(0, 7)}-08` }], can_book: true,
    }));
    renderizarProducto(sesion, '/equipos/1');
    const usuario = userEvent.setup();
    expect(await screen.findByRole('cell', { name: `${formatearFecha(`${mes}-06`)}: Ocupado` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Consultar disponibilidad' })).not.toBeInTheDocument();
    expect(screen.queryByText(/selecciona.*para conocer la disponibilidad/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(api.crearMiReserva).not.toHaveBeenCalled();

    await usuario.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    await usuario.click(await screen.findByRole('button', { name: `${formatearFecha(seleccionado.start_date)}: Disponible` }));
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    await usuario.click(screen.getByRole('button', { name: `${formatearFecha(seleccionado.end_date)}: Disponible` }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledExactlyOnceWith(1, seleccionado, expect.anything());
    expect(screen.getByTestId('location')).toHaveTextContent(`start_date=${seleccionado.start_date}&end_date=${seleccionado.end_date}`);
    expect(api.crearMiReserva).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.crearMiReserva).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...seleccionado }, expect.any(String));
  });

  it("muestra el error de un intervalo invertido de la URL sin solicitar disponibilidad", async () => {
    renderizarProducto(sesion, '/equipos/1?start_date=2027-11-12&end_date=2027-11-10');
    expect(await screen.findByText('La fecha de fin debe ser posterior al inicio.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("limpia las fechas seleccionadas y la disponibilidad anterior al cambiar fechas", async () => {
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Cambiar fechas' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.getByTestId('location')).toHaveTextContent('/equipos/1');
    expect(screen.getByTestId('location').textContent).not.toContain('start_date');
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(1);
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("rechaza un inicio pasado antes de enviar una reserva de cliente", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockResolvedValue({ equipment_id: 1, start_date: '2020-01-01', end_date: '2020-01-03', available: true, status: 'available' });
    renderizarProducto(sesion, '/equipos/1?start_date=2020-01-01&end_date=2020-01-03');
    expect(await screen.findByText('Elige hoy o una fecha posterior para reservar.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("ofrece a administración su propio panel sin exponer la confirmación de clientes", async () => {
    renderizarProducto({ ...sesion, role: 'admin', user: { ...sesion.user!, role: 'admin' } });
    expect(await screen.findByRole('link', { name: 'Ir al panel' })).toHaveAttribute('href', '/admin');
    expect(screen.queryByRole('button', { name: 'Confirmar reserva' })).not.toBeInTheDocument();
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("explica un bloqueo global de reservas y deshabilita la confirmación aunque una consulta anterior indicara disponibilidad", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: false });
    renderizarProducto();
    expect(await screen.findByText('Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("rechaza desde el calendario un intervalo completo no disponible aunque una consulta anterior indicara disponibilidad", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true, unavailable_end_dates: ['2027-11-12'] });
    renderizarProducto();
    expect(await screen.findByText('No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("mantiene bloqueada la confirmación cuando falla el calendario y permite reintentar su disponibilidad", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockRejectedValueOnce(new ErrorApi('Sin conexión.', 0));
    renderizarProducto();
    const usuario = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.crearMiReserva).not.toHaveBeenCalled();

    await usuario.click(screen.getByRole('button', { name: 'Reintentar calendario' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(screen.getByText('Disponible del 10/11/2027 al 12/11/2027.')).toBeInTheDocument();
    expect(api.obtenerCalendarioDisponibilidadPublica).toHaveBeenCalledTimes(2);
    expect(api.crearMiReserva).not.toHaveBeenCalled();
  });

  it("distingue una espera temporal de base de datos de un intervalo no disponible y conserva las fechas elegidas", async () => {
    vi.mocked(api.crearMiReserva).mockRejectedValueOnce(new ErrorApi('Base ocupada temporalmente.', 503));
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El sistema está ocupado temporalmente.');
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' })).toBeEnabled();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('heading', { name: 'Reserva #42' })).not.toBeInTheDocument();
  });

  it("conserva la confirmación persistida y su foco si falla la actualización posterior del calendario", async () => {
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockResolvedValueOnce({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true })
      .mockRejectedValueOnce(new ErrorApi('Sin conexión.', 0));
    renderizarProducto();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    expect(screen.getByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(screen.getByText('Tu reserva se ha confirmado.')).toBeInTheDocument();
    expect(api.crearMiReserva).toHaveBeenCalledTimes(1);
  });
});
