import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErrorApi, type SesionAutenticacion, type ReservaCliente, type EquipoPublico } from '../api/cliente';
import { ContextoAutenticacion } from '../autenticacion/contexto';
import { destinoPermitido, destinoTrasAcceso } from '../autenticacion/destinos';
import { BotonGuardarProducto } from './BotonGuardarProducto';
import PaginaProductosGuardados from './PaginaProductosGuardados';
import { ProveedorProductosGuardados } from './ProveedorProductosGuardados';
import { useProductosGuardados } from './contextoProductosGuardados';

const fechas = { start_date: '2027-11-17', end_date: '2027-11-20' };
const sesion: SesionAutenticacion = { authenticated: true, username: 'ana@example.test', expires_at: '2027-12-01T12:00:00Z', role: 'customer', user: { id: 4, name: 'Ana', email: 'ana@example.test', role: 'customer', active: true } };
const productos: EquipoPublico[] = [
  { id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: '', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
  { id: 2, name: 'Micrófono Brisa', category: 'Sonido', public_description: '', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
];

function Cantidad() { const guardado = useProductosGuardados(); return <output aria-label="Guardados">{guardado.ids.length}</output>; }
function renderizarLista(ruta = '/mi-lista?start_date=2027-11-17&end_date=2027-11-20') {
  return render(<ContextoAutenticacion.Provider value={{ sesion, comprobando: false, errorComprobacion: null, caducado: false, iniciarSesion: vi.fn(), cerrarSesionUsuario: vi.fn(), comprobarSesion: vi.fn() }}><MemoryRouter initialEntries={[ruta]}><ProveedorProductosGuardados cliente><Cantidad /><PaginaProductosGuardados /></ProveedorProductosGuardados></MemoryRouter></ContextoAutenticacion.Provider>);
}
function botonConfirmar() { return screen.getByRole('button', { name: 'Reservar 2 equipos a la vez' }); }

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2027-11-01T12:00:00Z'));
  vi.spyOn(api, 'listarProductosGuardados').mockResolvedValue({ equipment_ids: [1, 2] });
  vi.spyOn(api, 'obtenerEquipoPublico').mockImplementation(async (id) => productos.find((elementoLista) => elementoLista.id === id)!);
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' }));
  vi.spyOn(api, 'obtenerCalendarioDisponibilidadPublica').mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, start_date: intervalo.start_date, end_date: intervalo.end_date, can_book: true, occupied_ranges: [], unavailable_end_dates: [] }));
  vi.spyOn(api, 'eliminarProductoGuardado').mockResolvedValue({ equipment_ids: [2] });
  vi.spyOn(api, 'crearMisReservasConjuntas').mockImplementation(async (entrada) => entrada.equipment_ids.map((id_equipo, indice) => ({ equipment_id: id_equipo, id: 41 + indice, start_date: entrada.start_date, end_date: entrada.end_date, status: 'confirmed' })));
});
afterEach(() => { vi.useRealTimers(); });

describe("Mi lista y reserva conjunta", () => {
  it("recupera un lote de un producto al recargar y reintenta la misma intención pese a la disponibilidad completa", async () => {
    vi.mocked(api.crearMisReservasConjuntas).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    const primero = renderizarLista();
    const usuario = userEvent.setup();
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    await usuario.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No hemos podido comprobar si se confirmó la reserva conjunta.');
    const key = vi.mocked(api.crearMisReservasConjuntas).mock.calls[0]![1];
    primero.unmount();
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo!, available: false, status: 'unavailable' }));
    renderizarLista();
    const reintento = await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    expect(reintento).toBeEnabled();
    expect(await screen.findByRole('checkbox', { name: 'Seleccionar Cámara Aurora S4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).not.toBeChecked();
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledTimes(1);
    await usuario.click(reintento);
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.crearMisReservasConjuntas).toHaveBeenNthCalledWith(2, { equipment_ids: [1], ...fechas }, key);
  });

  it("reutiliza la clave de un lote de varios productos si falla el servidor y crea otra al cambiar la selección", async () => {
    vi.mocked(api.crearMisReservasConjuntas).mockRejectedValueOnce(new ErrorApi('Lost response', 500));
    renderizarLista();
    const usuario = userEvent.setup();
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    await usuario.click(botonConfirmar());
    const key = vi.mocked(api.crearMisReservasConjuntas).mock.calls[0]![1];
    await usuario.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(api.crearMisReservasConjuntas).toHaveBeenNthCalledWith(2, { equipment_ids: [1, 2], ...fechas }, key);
    await usuario.click(await screen.findByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(vi.mocked(api.crearMisReservasConjuntas).mock.calls[2]![1]).not.toBe(key);
  });

  it("conserva lotes completados durante la carga asíncrona de la lista guardada y permite otra operación deliberada", async () => {
    const primero = renderizarLista();
    const usuario = userEvent.setup();
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    await usuario.click(botonConfirmar());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    const key = vi.mocked(api.crearMisReservasConjuntas).mock.calls[0]![1];
    primero.unmount();
    renderizarLista();
    await screen.findByRole('region', { name: 'Reserva conjunta registrada' });
    expect(screen.queryByRole('button', { name: 'Reservar 2 equipos a la vez' })).not.toBeInTheDocument();
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    await usuario.click(botonConfirmar());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(vi.mocked(api.crearMisReservasConjuntas).mock.calls[1]![1]).not.toBe(key);
  });

  it("recupera identificadores originales del lote cuando cambian los productos canónicos activos tras perder una respuesta", async () => {
    vi.mocked(api.listarProductosGuardados).mockResolvedValue({ equipment_ids: [1] });
    vi.mocked(api.crearMisReservasConjuntas).mockRejectedValueOnce(new ErrorApi('Lost response', 0));
    const primero = renderizarLista();
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.crearMisReservasConjuntas).mock.calls[0]![1];
    primero.unmount();
    vi.mocked(api.listarProductosGuardados).mockResolvedValue({ equipment_ids: [2] });
    renderizarLista();
    expect(await screen.findByText('Tu lista ha cambiado desde la reserva anterior. Consulta o recupera esa operación antes de preparar otra.')).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.crearMisReservasConjuntas).toHaveBeenNthCalledWith(2, { equipment_ids: [1], ...fechas }, key);
    await usuario.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.crearMisReservasConjuntas).toHaveBeenNthCalledWith(3, { equipment_ids: [2], ...fechas }, expect.any(String));
    expect(vi.mocked(api.crearMisReservasConjuntas).mock.calls[2]![1]).not.toBe(key);
  });

  it("selecciona todos los productos inicialmente, muestra sus fechas y confirma una vez conservando favoritos", async () => {
    renderizarLista();
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Cámara Aurora S4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).toBeChecked();
    expect(screen.getAllByText('Disponible para todo el periodo')).toHaveLength(2);
    expect(screen.getByText('Todos disponibles del 17/11/2027 al 20/11/2027.')).toBeInTheDocument();
    fireEvent.click(botonConfirmar());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1, 2], ...fechas }, expect.any(String));
    expect(api.eliminarProductoGuardado).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('2');
    await waitFor(() => expect(screen.getByRole('heading', { name: '2 reservas confirmadas' })).toHaveFocus());
    expect(screen.getByRole('link', { name: 'Reserva #41 · Cámara Aurora S4' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(screen.getByRole('link', { name: 'Ver mis reservas' })).toHaveAttribute('href', '/mis-reservas');
  });

  it("compara la intersección del calendario compartido y permite seleccionar un subconjunto disponible", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => id_equipo === 1 ? { equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' } : { equipment_id: id_equipo, ...intervalo!, available: false, status: 'unavailable' });
    vi.mocked(api.obtenerCalendarioDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, start_date: intervalo.start_date, end_date: intervalo.end_date, can_book: true, occupied_ranges: id_equipo === 2 ? [{ start_date: '2027-11-18', end_date: '2027-11-19' }] : [], unavailable_end_dates: id_equipo === 2 ? ['2027-11-20'] : [] }));
    renderizarLista();
    expect(await screen.findByText('No disponible para todo el periodo')).toBeInTheDocument();
    await waitFor(() => expect(botonConfirmar()).toBeDisabled());
    expect(screen.getByRole('button', { name: /^18\/11\/2027: Ocupado/ })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1], ...fechas }, expect.any(String));
  });

  it("etiqueta modelos recién confirmados como reservados tras actualizar disponibilidad y conserva el estado de los no seleccionados", async () => {
    let confirmado = false;
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => id_equipo === 1 && !confirmado
      ? { equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' }
      : { equipment_id: id_equipo, ...intervalo!, available: false, status: 'unavailable' });
    vi.mocked(api.crearMisReservasConjuntas).mockImplementation(async (entrada) => {
      confirmado = true;
      return [{ equipment_id: 99, id: 41, start_date: entrada.start_date, end_date: entrada.end_date, status: 'confirmed' }];
    });
    renderizarLista();
    await screen.findByText('No disponible para todo el periodo');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(4));
    expect(await screen.findByText('Reservado del 17/11/2027 al 20/11/2027')).toHaveClass('is-available');
    expect(screen.getAllByText('No disponible para todo el periodo')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Reserva #41 · Cámara Aurora S4' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    expect(screen.queryByText('Reservado del 17/11/2027 al 20/11/2027')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('No disponible para todo el periodo')).toHaveLength(2));
  });

  it("rechaza la doble confirmación y bloquea fechas y selección de productos mientras espera la solicitud atómica", async () => {
    let resolver: ((valor: ReservaCliente[]) => void) | undefined;
    vi.mocked(api.crearMisReservasConjuntas).mockImplementation(() => new Promise((terminado) => { resolver = terminado; }));
    renderizarLista();
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    const boton = botonConfirmar(); fireEvent.click(boton); fireEvent.click(boton);
    expect(screen.getByRole('button', { name: 'Confirmando todos los equipos…' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toBeDisabled();
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledTimes(1);
    await act(async () => resolver?.([1, 2].map((id_equipo, indice) => ({ equipment_id: id_equipo, id: 41 + indice, ...fechas, status: 'confirmed' }))));
    expect(await screen.findByRole('heading', { name: '2 reservas confirmadas' })).toBeInTheDocument();
  });

  it("permite un subconjunto disponible si falla la consulta de disponibilidad de un producto excluido", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => {
      if (id_equipo === 2) throw new ErrorApi('No se pudo conectar', 0);
      return { equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' };
    });
    renderizarLista();
    await screen.findByRole('button', { name: 'Reintentar disponibilidad' });
    expect(botonConfirmar()).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1], ...fechas }, expect.any(String));
  });

  it("comprueba todos los modelos seleccionados antes de ofrecer una devolución en un mes posterior", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => id_equipo === 2 && intervalo?.end_date === '2027-12-01'
      ? { equipment_id: id_equipo, ...intervalo!, available: false, status: 'unavailable' }
      : { equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' });
    renderizarLista(); await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Fecha de devolución: 20/11/2027' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(2, { start_date: '2027-11-17', end_date: '2027-12-01' }, expect.any(AbortSignal)));
    expect(screen.getByRole('button', { name: /^02\/12\/2027: Disponible/ })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('button', { name: /^02\/12\/2027: Disponible/ }));
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 20/11/2027' })).toBeInTheDocument();
  });

  it("conserva todos los favoritos y consulta ambos productos de nuevo tras un 409 sin mostrar un éxito parcial", async () => {
    vi.mocked(api.crearMisReservasConjuntas).mockRejectedValue(new ErrorApi('Ocupado', 409));
    renderizarLista(); await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    fireEvent.click(botonConfirmar());
    expect(await screen.findByText(/La disponibilidad ha cambiado\. No se ha reservado ningún equipo/)).toBeInTheDocument();
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(4));
    expect(screen.queryByRole('heading', { name: '2 reservas confirmadas' })).not.toBeInTheDocument();
    expect(api.crearMisReservasConjuntas).toHaveBeenCalledTimes(1);
    expect(api.eliminarProductoGuardado).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('2');
  });

  it("conserva identificadores guardados no disponibles, bloquea confirmar y permite al cliente eliminar uno", async () => {
    vi.mocked(api.obtenerEquipoPublico).mockImplementation(async (id) => { if (id === 1) throw new ErrorApi('No existe', 404); return productos[1]!; });
    renderizarLista();
    expect(await screen.findByText('Este equipo ya no está en el catálogo. Puedes quitarlo de tu lista.')).toBeInTheDocument();
    expect(botonConfirmar()).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Equipo #1 de mi lista' }));
    await waitFor(() => expect(screen.getByLabelText('Guardados')).toHaveTextContent('1'));
    expect(api.eliminarProductoGuardado).toHaveBeenCalledExactlyOnceWith(1);
    expect(screen.queryByRole('heading', { name: 'Equipo #1' })).not.toBeInTheDocument();
  });

  it("ofrece calendarios individuales por producto sin alterar el periodo compartido seleccionado", async () => {
    renderizarLista(); await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Ver calendario de Cámara Aurora S4' }));
    const calendario = await screen.findByRole('region', { name: 'Calendario de Cámara Aurora S4' });
    expect(within(calendario).getByText('noviembre de 2027')).toBeInTheDocument();
    expect(botonConfirmar()).toBeEnabled();
    expect(api.crearMisReservasConjuntas).not.toHaveBeenCalled();
  });

  it("actualiza los modelos canónicos guardados cuando desaparece una unidad representativa", async () => {
    vi.mocked(api.listarProductosGuardados).mockResolvedValueOnce({ equipment_ids: [1] }).mockResolvedValueOnce({ equipment_ids: [2] });
    vi.mocked(api.obtenerEquipoPublico).mockImplementation(async (id) => { if (id === 1) throw new ErrorApi('No existe', 404); return productos[1]!; });
    renderizarLista();
    await screen.findByRole('heading', { name: 'Equipo #1' });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar mi lista' }));
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    expect(api.listarProductosGuardados).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('heading', { name: 'Equipo #1' })).not.toBeInTheDocument();
  });

  it("muestra una lista vacía y un fallo de consulta que permite reintentar", async () => {
    vi.mocked(api.listarProductosGuardados).mockRejectedValueOnce(new ErrorApi('Sin conexión', 0)).mockResolvedValueOnce({ equipment_ids: [] });
    renderizarLista();
    expect(await screen.findByRole('alert')).toHaveTextContent('Sin conexión');
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar mi lista' }));
    expect(await screen.findByRole('heading', { name: 'Tu próximo proyecto empieza aquí' })).toBeInTheDocument();
    expect(api.crearMisReservasConjuntas).not.toHaveBeenCalled();
  });

  it("bloquea por precaución ante un fallo de calendario o disponibilidad y conserva la selección para reintentar", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockRejectedValue(new ErrorApi('Sin conexión', 0));
    renderizarLista();
    expect(await screen.findByRole('button', { name: 'Reintentar disponibilidad' })).toBeInTheDocument();
    expect(botonConfirmar()).toBeDisabled();
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id_equipo, intervalo) => ({ equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar disponibilidad' }));
    await waitFor(() => expect(botonConfirmar()).toBeEnabled());
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it("impide confirmar periodos no válidos o pasados", async () => {
    renderizarLista('/mi-lista?start_date=2027-10-17&end_date=2027-10-20');
    expect(await screen.findByText('Elige hoy o una fecha posterior para reservar.')).toBeInTheDocument();
    expect(botonConfirmar()).toBeDisabled();
    expect(api.crearMisReservasConjuntas).not.toHaveBeenCalled();
  });

  it("ignora la respuesta de un periodo anterior después de cambiar las fechas compartidas", async () => {
    let finalizar: ((valor: Awaited<ReturnType<typeof api.obtenerDisponibilidadPublica>>) => void) | undefined;
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation((id_equipo, intervalo) => id_equipo === 1 ? new Promise((terminado) => { finalizar = terminado; }) : Promise.resolve({ equipment_id: id_equipo, ...intervalo!, available: true, status: 'available' }));
    renderizarLista();
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: /^21\/11\/2027: Disponible/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /^21\/11\/2027: Disponible/ }));
    await act(async () => finalizar?.({ equipment_id: 1, ...fechas, available: true, status: 'available' }));
    expect(botonConfirmar()).toBeDisabled();
    expect(api.crearMisReservasConjuntas).not.toHaveBeenCalled();
  });
});

describe("controles de guardado y aislamiento entre cuentas", () => {
  it("persiste el guardado y la eliminación mediante el servidor, actualiza el contador compartido y sobrevive a un proveedor nuevo", async () => {
    vi.mocked(api.listarProductosGuardados).mockResolvedValueOnce({ equipment_ids: [] }).mockResolvedValueOnce({ equipment_ids: [1] });
    vi.spyOn(api, 'guardarProducto').mockResolvedValue({ equipment_ids: [1] });
    const vista = render(<MemoryRouter><ProveedorProductosGuardados cliente><Cantidad /><BotonGuardarProducto id={1} nombre="Cámara Aurora S4" /></ProveedorProductosGuardados></MemoryRouter>);
    const usuario = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar Cámara Aurora S4 en mi lista' })).toBeEnabled());
    await usuario.click(screen.getByRole('button', { name: 'Guardar Cámara Aurora S4 en mi lista' }));
    expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('1');
    expect(api.guardarProducto).toHaveBeenCalledExactlyOnceWith(1);
    vista.unmount();
    render(<MemoryRouter><ProveedorProductosGuardados cliente><BotonGuardarProducto id={1} nombre="Cámara Aurora S4" /></ProveedorProductosGuardados></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toBeEnabled());
  });

  it("conserva fechas en destinos de acceso de visitantes y permite volver a Mi lista de forma segura", () => {
    render(<MemoryRouter initialEntries={['/equipos/1?start_date=2027-11-17&end_date=2027-11-20']}><BotonGuardarProducto id={1} nombre="Cámara Aurora S4" /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Acceder para guardar Cámara Aurora S4 en mi lista' })).toHaveAttribute('href', '/acceso?next=%2Fequipos%2F1%3Fstart_date%3D2027-11-17%26end_date%3D2027-11-20');
    expect(destinoPermitido('/mi-lista?start_date=2027-11-17&end_date=2027-11-20')).toBe('/mi-lista?start_date=2027-11-17&end_date=2027-11-20');
    expect(destinoTrasAcceso('customer', '/mi-lista')).toBe('/mi-lista');
    expect(destinoPermitido('//evil.test/mi-lista')).toBeNull();
    expect(api.listarProductosGuardados).not.toHaveBeenCalled();
  });

  it("impide que la respuesta de una cuenta anterior cambie la lista de la siguiente", async () => {
    let finalizar: ((valor: { equipment_ids: number[] }) => void) | undefined;
    vi.mocked(api.listarProductosGuardados).mockImplementationOnce(() => new Promise((terminado) => { finalizar = terminado; })).mockResolvedValueOnce({ equipment_ids: [2] });
    const vista = render(<ProveedorProductosGuardados key="customer-1" cliente><Cantidad /></ProveedorProductosGuardados>);
    await waitFor(() => expect(api.listarProductosGuardados).toHaveBeenCalledTimes(1));
    vista.rerender(<ProveedorProductosGuardados key="customer-2" cliente><Cantidad /></ProveedorProductosGuardados>);
    await waitFor(() => expect(screen.getByLabelText('Guardados')).toHaveTextContent('1'));
    await act(async () => finalizar?.({ equipment_ids: [1, 2] }));
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('1');
  });
});
