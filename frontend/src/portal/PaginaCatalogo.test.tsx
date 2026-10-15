import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type EquipoPublico } from '../api/cliente';
import { PaginaCatalogo } from './PaginaCatalogo';
import { recordarPosicionCatalogo } from './navegacionCatalogo';

const equipo: EquipoPublico[] = [
  { id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: 'Entrevistas.', technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
  { id: 2, name: 'Micrófono Brisa', category: 'Sonido', public_description: 'Sonido.', technical_specs: {}, image_url: 'https://example.test/microphone.webp', image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 4 },
];

function renderizarCatalogo(ruta = '/catalogo') {
  function Navegacion() {
    const ubicacion = useLocation();
    const navegar = useNavigate();
    return <><output aria-label="Consulta aplicada">{ubicacion.search}</output><button onClick={() => { void navegar(-1); }}>Atrás</button><button onClick={() => { void navegar(1); }}>Adelante</button><PaginaCatalogo /></>;
  }
  return render(<MemoryRouter initialEntries={[ruta]}><Navegacion /></MemoryRouter>);
}

function elegirFecha(campo: 'inicio' | 'fin', fecha: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Fecha de ${campo}:`) }));
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).getByRole('button', { name: fecha.split('-').reverse().join('/') }));
}

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2027-11-01T12:00:00Z'));
  vi.spyOn(api, 'listarEquiposPublicos').mockResolvedValue(equipo);
  vi.spyOn(api, 'obtenerDisponibilidadPublica').mockImplementation(async (id, intervalo) => id === 1 ? { equipment_id: id, start_date: intervalo!.start_date, end_date: intervalo!.end_date, status: 'available', available: true } : { equipment_id: id, start_date: intervalo!.start_date, end_date: intervalo!.end_date, status: 'unavailable', available: false });
});
afterEach(() => { vi.useRealTimers(); });

describe("catálogo público", () => {
  it("restaura la posición recordada de resultados solo después de cargar las tarjetas asíncronas", async () => {
    const ruta = '/catalogo?q=Aurora';
    vi.spyOn(window, 'scrollY', 'get').mockReturnValue(940);
    recordarPosicionCatalogo(ruta);
    const desplazamientoPagina = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((funcionRetorno) => window.setTimeout(() => funcionRetorno(0), 0));
    let finalizar!: (elementos: EquipoPublico[]) => void;
    const pendiente = new Promise<EquipoPublico[]>((resolver) => { finalizar = resolver; });
    vi.mocked(api.listarEquiposPublicos).mockReturnValue(pendiente);
    renderizarCatalogo(ruta);
    expect(desplazamientoPagina).not.toHaveBeenCalled();
    await act(async () => { finalizar(equipo); });
    await screen.findByRole('heading', { name: equipo[0]!.name });
    await waitFor(() => expect(desplazamientoPagina).toHaveBeenCalledExactlyOnceWith({ top: 940, left: 0, behavior: 'instant' }));
    const enlace = new URL(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' }).getAttribute('href')!, 'https://rentalab.invalid');
    expect(enlace.searchParams.get('catalogue')).toBe(ruta);
  });

  it("abre las fechas del modelo elegido sin salir del catálogo ni cambiar las fechas de alquiler aplicadas", async () => {
    vi.spyOn(api, 'obtenerFechasReservaPublica').mockResolvedValue({ equipment_id: 2, reservations: [{ start_date: '2027-11-01', end_date: '2027-11-04' }] });
    renderizarCatalogo('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    expect(api.obtenerFechasReservaPublica).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Ver fechas de 4 reservas de Micrófono Brisa' }));
    const region = await screen.findByRole('region', { name: 'Fechas de las reservas de Micrófono Brisa' });
    expect(await within(region).findByText('01/11/2027')).toBeInTheDocument();
    expect(within(region).getByText('04/11/2027')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?start_date=2027-11-10&end_date=2027-11-12');
    expect(screen.getByRole('link', { name: 'Ver Micrófono Brisa' })).toHaveAttribute('href', '/equipos/2?start_date=2027-11-10&end_date=2027-11-12');
    expect(api.obtenerFechasReservaPublica).toHaveBeenCalledExactlyOnceWith(2, expect.any(AbortSignal));
  });

  it("muestra el recuento de reservas de cada modelo junto a su acción independientemente de la disponibilidad de hoy", async () => {
    renderizarCatalogo();
    await screen.findByText('No disponible hoy');
    for (const elementoLista of equipo) {
      const tarjeta = screen.getByRole('heading', { name: elementoLista.name }).closest('li')!;
      const cantidad = within(tarjeta).getByText(`${elementoLista.active_reservations_count} reservas`);
      expect(cantidad).toBeInTheDocument();
      expect(within(tarjeta).getByText('En curso y próximas')).toBeInTheDocument();
      expect(within(tarjeta).getByRole('link', { name: 'Ver equipo' }).parentElement).toContainElement(cantidad);
    }
  });

  it("conserva el recuento global para las fechas seleccionadas y lo actualiza al recargar el catálogo", async () => {
    vi.mocked(api.listarEquiposPublicos).mockResolvedValue([{ ...equipo[1]!, active_reservations_count: 1 }]);
    renderizarCatalogo('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('No disponible para tus fechas');
    expect(screen.getByText('1 reserva')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver equipo' })).toHaveAttribute('href', '/equipos/2?start_date=2027-11-10&end_date=2027-11-12');
    vi.mocked(api.listarEquiposPublicos).mockResolvedValue([{ ...equipo[1]!, active_reservations_count: 0 }]);
    fireEvent.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('0 reservas');
    expect(screen.queryByText('1 reserva')).not.toBeInTheDocument();
  });

  it("muestra en verde y rojo la disponibilidad real de hoy sin aplicar fechas a la búsqueda ni a los enlaces de producto", async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T12:00:00Z'));
    renderizarCatalogo();
    expect(await screen.findByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Sonido' })).toBeInTheDocument();
    expect(screen.getByText('Disponible hoy').closest('p')).toHaveClass('is-available');
    expect(screen.getByText('No disponible hoy').closest('p')).toHaveClass('is-unavailable');
    expect(screen.queryByText('Selecciona fechas para ver disponibilidad')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledTimes(2);
    for (const elementoLista of equipo) {
      expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(elementoLista.id, { start_date: '2026-10-15', end_date: '2026-10-16' }, expect.any(AbortSignal));
    }
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1');
  });

  it("filtra hoy inmediatamente sin fechas y restaura todos los equipos al desmarcar con el teclado", async () => {
    renderizarCatalogo();
    await screen.findByText('No disponible hoy');
    const usuario = userEvent.setup();
    const casilla = screen.getByRole('checkbox', { name: 'Solo disponibles' });
    casilla.focus();
    await usuario.keyboard(' ');
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(casilla).toBeChecked();
    expect(screen.getByText('Disponible hoy')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?available=1');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1?catalogue=%2Fcatalogo%3Favailable%3D1');
    await usuario.keyboard(' ');
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(casilla).not.toBeChecked();
  });

  it("restaura desde la URL el filtro de disponibles sin fechas y conserva los borradores incompletos al alternarlo", async () => {
    renderizarCatalogo('/catalogo?available=1');
    await screen.findByText('Disponible hoy');
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
    elegirFecha('inicio', '2027-11-10');
    const casilla = screen.getByRole('checkbox', { name: 'Solo disponibles' });
    expect(casilla).toBeChecked();
    fireEvent.click(casilla);
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
  });

  it.each([
    ['2026-10-15T22:30:00Z', '2026-10-16', '2026-10-17'],
    ['2026-01-30T23:30:00Z', '2026-01-31', '2026-02-01'],
    ['2026-12-30T23:30:00Z', '2026-12-31', '2027-01-01'],
    ['2026-03-28T23:30:00Z', '2026-03-29', '2026-03-30'],
  ])("usa el día del calendario de Madrid y el siguiente día excluido a las %s", async (ahora, hoy, manana) => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(ahora));
    renderizarCatalogo();
    await screen.findByText('Disponible hoy');
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: hoy, end_date: manana }, expect.any(AbortSignal));
  });

  it("comprueba el día nuevo al volver al catálogo después de la medianoche de Madrid", async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T21:30:00Z'));
    renderizarCatalogo();
    await screen.findByText('Disponible hoy');
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2026-10-15', end_date: '2026-10-16' }, expect.any(AbortSignal));
    vi.mocked(api.obtenerDisponibilidadPublica).mockClear();
    vi.setSystemTime(new Date('2026-10-15T22:30:00Z'));
    fireEvent.focus(window);
    await waitFor(() => expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2026-10-16', end_date: '2026-10-17' }, expect.any(AbortSignal)));
    expect(await screen.findByText('Disponible hoy')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
  });

  it("evita marcar equipos como disponibles si falla la consulta de hoy y permite reintentarla", async () => {
    vi.mocked(api.obtenerDisponibilidadPublica).mockRejectedValue(new Error('No se pudo consultar la disponibilidad.'));
    renderizarCatalogo();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo consultar la disponibilidad.');
    expect(screen.queryByText('Disponible hoy')).not.toBeInTheDocument();
    expect(screen.queryByText('No disponible hoy')).not.toBeInTheDocument();
    vi.mocked(api.obtenerDisponibilidadPublica).mockImplementation(async (id, intervalo) => ({ equipment_id: id, start_date: intervalo!.start_date, end_date: intervalo!.end_date, status: 'available', available: true }));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Volver a cargar' }));
    expect(await screen.findAllByText('Disponible hoy')).toHaveLength(2);
  });

  it("combina búsqueda y categoría mediante la API pública sin perder las opciones de todas las categorías", async () => {
    vi.mocked(api.listarEquiposPublicos).mockImplementation(async (filtros) => filtros?.q || filtros?.category ? [equipo[0]!] : equipo);
    renderizarCatalogo();
    const usuario = userEvent.setup();
    await screen.findByRole('option', { name: 'Sonido' });
    await usuario.type(screen.getByRole('searchbox', { name: 'Buscar equipo' }), 'Aurora');
    await usuario.selectOptions(screen.getByLabelText('Categoría'), 'Cámaras');
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await waitFor(() => expect(api.listarEquiposPublicos).toHaveBeenLastCalledWith({ q: 'Aurora', category: 'Cámaras' }, expect.any(AbortSignal)));
    expect(screen.getByRole('option', { name: 'Sonido' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
  });

  it("consulta las fechas seleccionadas, filtra solo resultados explícitamente disponibles y conserva las fechas en enlaces de producto", async () => {
    renderizarCatalogo('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    const usuario = userEvent.setup();
    await screen.findByText('Disponible para tus fechas');
    expect(screen.getByText('No disponible para tus fechas').closest('p')).toHaveClass('is-unavailable');
    expect(screen.queryByText('Disponible hoy')).not.toBeInTheDocument();
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2027-11-10', end_date: '2027-11-12' }, expect.any(AbortSignal));
    await usuario.click(screen.getByRole('checkbox', { name: 'Solo disponibles' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(await screen.findByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(screen.queryByText(/avería|reserva #|cliente@/i)).not.toBeInTheDocument();
  });

  it("selecciona y limpia fechas del calendario como borradores hasta consultar el catálogo", async () => {
    renderizarCatalogo();
    const usuario = userEvent.setup();
    await screen.findByText('Disponible hoy');
    vi.mocked(api.obtenerDisponibilidadPublica).mockClear();
    elegirFecha('inicio', '2027-11-10');
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).getByRole('button', { name: '12/11/2027' }));
    expect(screen.queryByRole('dialog', { name: 'Fechas del alquiler' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: 12/11/2027' })).toHaveFocus();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1');
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('Disponible para tus fechas');
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2027-11-10', end_date: '2027-11-12' }, expect.any(AbortSignal));
    vi.mocked(api.obtenerDisponibilidadPublica).mockClear();
    await usuario.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' }));
    await usuario.click(screen.getByRole('button', { name: 'Borrar fechas' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('Disponible hoy');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2027-11-01', end_date: '2027-11-02' }, expect.any(AbortSignal));
  });

  it("rechaza fechas incompletas sin sustituir la disponibilidad de hoy ya consultada", async () => {
    renderizarCatalogo();
    const usuario = userEvent.setup();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.obtenerDisponibilidadPublica).mockClear();
    elegirFecha('inicio', '2027-11-10');
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    expect(await screen.findByRole('alert')).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toHaveAttribute('aria-invalid', 'true');
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    expect(screen.getByText('Disponible hoy').closest('p')).toHaveClass('is-available');
  });

  it("sustituye una imagen remota opcional fallida por la alternativa local proporcionada una sola vez", async () => {
    renderizarCatalogo();
    const imagen = await screen.findByRole('img', { name: 'Micrófono Brisa' });
    fireEvent.error(imagen);
    const alternativa = screen.getByRole('img', { name: 'Imagen de referencia para Micrófono Brisa' });
    expect(alternativa).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    fireEvent.error(alternativa);
    expect(alternativa).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    const tarjetaCamara = screen.getByRole('heading', { name: 'Cámara Aurora S4' }).closest('li');
    expect(within(tarjetaCamara!).getByRole('img')).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
  });

  it("etiqueta fotografías locales de ejemplo y conserva la alternativa cuando falla una", async () => {
    vi.mocked(api.listarEquiposPublicos).mockResolvedValue([{ ...equipo[0]!, image_url: '/api/public/images/demo-camera.jpg' }]);
    renderizarCatalogo();
    const imagen = await screen.findByRole('img', { name: 'Fotografía de ejemplo para Cámara Aurora S4' });
    expect(imagen).toHaveAttribute('src', '/api/public/images/demo-camera.jpg');
    expect(screen.getByText('Fotografía de ejemplo')).toBeInTheDocument();
    fireEvent.error(imagen);
    expect(screen.getByRole('img', { name: 'Imagen de referencia para Cámara Aurora S4' })).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    expect(screen.queryByText('Fotografía de ejemplo')).not.toBeInTheDocument();
  });

  it("mantiene los resultados estables antes del retardo de búsqueda y permite aplicarla inmediatamente con Enter", async () => {
    vi.mocked(api.listarEquiposPublicos).mockImplementation(async (filtros) => filtros?.q ? [equipo[0]!] : equipo);
    renderizarCatalogo();
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    vi.mocked(api.listarEquiposPublicos).mockClear();
    const usuario = userEvent.setup();
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    await usuario.click(entrada);
    fireEvent.change(entrada, { target: { value: 'Aurora' } });
    expect(entrada).toHaveFocus();
    expect(entrada).toHaveValue('Aurora');
    expect(screen.getByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.listarEquiposPublicos).not.toHaveBeenCalled();
    await usuario.keyboard('{Enter}');
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(api.listarEquiposPublicos).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora');
  });

  it("vincula disponibilidad y fechas de producto al intervalo aplicado hasta enviar filtros válidos del borrador", async () => {
    renderizarCatalogo('/catalogo?q=Aurora&start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('Disponible para tus fechas');
    vi.mocked(api.listarEquiposPublicos).mockClear();
    vi.mocked(api.obtenerDisponibilidadPublica).mockClear();
    const usuario = userEvent.setup();
    elegirFecha('inicio', '2027-11-20');
    await usuario.selectOptions(screen.getByLabelText('Categoría'), 'Cámaras');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(api.listarEquiposPublicos).not.toHaveBeenCalled();
    expect(api.obtenerDisponibilidadPublica).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    expect(await screen.findByRole('alert')).toHaveFocus();
    expect(api.listarEquiposPublicos).not.toHaveBeenCalled();
    elegirFecha('fin', '2027-11-22');
    await usuario.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-20&end_date=2027-11-22')));
    expect(api.listarEquiposPublicos).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: 'Cámaras' }, expect.any(AbortSignal));
    expect(api.obtenerDisponibilidadPublica).toHaveBeenCalledWith(1, { start_date: '2027-11-20', end_date: '2027-11-22' }, expect.any(AbortSignal));
  });

  it("restaura campos con el historial del navegador y reinicia filtros aplicados y borradores al limpiar una búsqueda vacía", async () => {
    vi.mocked(api.listarEquiposPublicos).mockImplementation(async (filtros) => filtros?.q === 'Nada' ? [] : equipo);
    renderizarCatalogo();
    const usuario = userEvent.setup();
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    await usuario.click(entrada);
    fireEvent.change(entrada, { target: { value: 'Aurora' } });
    await usuario.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora'));
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    elegirFecha('inicio', '2027-11-20');
    await usuario.click(screen.getByRole('button', { name: 'Atrás' }));
    expect(entrada).toHaveValue('');
    await usuario.click(screen.getByRole('button', { name: 'Adelante' }));
    expect(entrada).toHaveValue('Aurora');
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    await usuario.click(entrada);
    fireEvent.change(entrada, { target: { value: 'Nada' } });
    await usuario.keyboard('{Enter}');
    await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' });
    elegirFecha('inicio', '2027-11-20');
    await usuario.click(screen.getByRole('button', { name: 'Ver todo el catálogo' }));
    expect(entrada).toHaveValue('');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
  });

  it("limpia un borrador sin enviar aunque el catálogo sin filtros esté vacío", async () => {
    vi.mocked(api.listarEquiposPublicos).mockResolvedValue([]);
    renderizarCatalogo();
    await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' });
    const usuario = userEvent.setup();
    await usuario.type(screen.getByRole('searchbox', { name: 'Buscar equipo' }), 'Aurora');
    await usuario.click(screen.getByRole('button', { name: 'Ver todo el catálogo' }));
    expect(screen.getByRole('searchbox', { name: 'Buscar equipo' })).toHaveValue('');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' })).toBeInTheDocument();
  });

  it("busca automáticamente una sola vez tras 150 ms y conserva las tarjetas y el foco mientras espera la red", async () => {
    let finalizar!: (valor: EquipoPublico[]) => void;
    vi.mocked(api.listarEquiposPublicos).mockImplementation((filtros) => filtros?.q ? new Promise((resolver) => { finalizar = resolver; }) : Promise.resolve(equipo));
    renderizarCatalogo();
    const camara = await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listarEquiposPublicos).mockClear();
    vi.useFakeTimers();
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    entrada.focus();
    for (let longitud = 1; longitud <= 'Aurora'.length; longitud++) fireEvent.change(entrada, { target: { value: 'Aurora'.slice(0, longitud) } });
    await act(() => vi.advanceTimersByTimeAsync(149));
    expect(api.listarEquiposPublicos).not.toHaveBeenCalled();
    expect(entrada).toHaveFocus();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(api.listarEquiposPublicos).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBe(camara);
    expect(screen.getByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Explora el catálogo' })).toHaveAttribute('aria-busy', 'true');
    expect(entrada).toHaveFocus();
    await act(async () => { finalizar([equipo[0]!]); });
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBe(camara);
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora');
    expect(entrada).toHaveFocus();
  });

  it("cancela la búsqueda anterior, ignora su respuesta tardía y restaura los resultados automáticamente al limpiar el campo", async () => {
    let finalizarAnterior!: (valor: EquipoPublico[]) => void;
    vi.mocked(api.listarEquiposPublicos).mockImplementation((filtros) => filtros?.q === 'Aurora' ? new Promise((resolver) => { finalizarAnterior = resolver; }) : Promise.resolve(filtros?.q ? [equipo[1]!] : equipo));
    renderizarCatalogo();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listarEquiposPublicos).mockClear();
    vi.useFakeTimers();
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    fireEvent.change(entrada, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    const senalAnterior = vi.mocked(api.listarEquiposPublicos).mock.calls[0]![1]!;
    fireEvent.change(entrada, { target: { value: 'Brisa' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(senalAnterior.aborted).toBe(true);
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    await act(async () => { finalizarAnterior([equipo[0]!]); });
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    expect(entrada).toHaveValue('Brisa');
    fireEvent.change(entrada, { target: { value: '' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
  });

  it("conserva categoría y borradores incompletos de fechas cuando la búsqueda en directo cambia solo la consulta de la URL", async () => {
    renderizarCatalogo('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('Disponible para tus fechas');
    vi.mocked(api.listarEquiposPublicos).mockClear();
    vi.useFakeTimers();
    elegirFecha('inicio', '2027-11-20');
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar equipo' }), { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(api.listarEquiposPublicos).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 20/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByLabelText('Categoría')).toHaveValue('Cámaras');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(screen.getByLabelText('Consulta aplicada')).not.toHaveTextContent('category=');
  });

  it("evita buscar durante la composición del texto o repetir la solicitud tras un Enter inmediato", async () => {
    renderizarCatalogo();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listarEquiposPublicos).mockClear();
    vi.useFakeTimers();
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    fireEvent.compositionStart(entrada);
    fireEvent.change(entrada, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(api.listarEquiposPublicos).not.toHaveBeenCalled();
    fireEvent.compositionEnd(entrada);
    fireEvent.submit(screen.getByRole('form', { name: 'Buscar en el catálogo' }));
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(api.listarEquiposPublicos).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
  });

  it("muestra un error asíncrono sin quitar el foco y reintenta la búsqueda actual", async () => {
    vi.mocked(api.listarEquiposPublicos).mockImplementation(async (filtros) => {
      if (filtros?.q) throw new Error('No se pudo actualizar el catálogo.');
      return equipo;
    });
    renderizarCatalogo();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.useFakeTimers();
    const entrada = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    entrada.focus();
    fireEvent.change(entrada, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(screen.getByRole('alert')).toHaveTextContent('No se pudo actualizar el catálogo.');
    expect(entrada).toHaveFocus();
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    vi.mocked(api.listarEquiposPublicos).mockResolvedValue([equipo[0]!]);
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Buscar equipo' })).toHaveValue('Aurora');
  });
});
