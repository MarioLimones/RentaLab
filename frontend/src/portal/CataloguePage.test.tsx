import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type PublicEquipment } from '../api/client';
import { CataloguePage } from './CataloguePage';
import { rememberCataloguePosition } from './catalogueNavigation';

const equipment: PublicEquipment[] = [
  { id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: 'Entrevistas.', technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
  { id: 2, name: 'Micrófono Brisa', category: 'Sonido', public_description: 'Sonido.', technical_specs: {}, image_url: 'https://example.test/microphone.webp', image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 4 },
];

function renderCatalogue(path = '/catalogo') {
  function Navigation() {
    const location = useLocation();
    const navigate = useNavigate();
    return <><output aria-label="Consulta aplicada">{location.search}</output><button onClick={() => { void navigate(-1); }}>Atrás</button><button onClick={() => { void navigate(1); }}>Adelante</button><CataloguePage /></>;
  }
  return render(<MemoryRouter initialEntries={[path]}><Navigation /></MemoryRouter>);
}

function chooseDate(field: 'inicio' | 'fin', date: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Fecha de ${field}:`) }));
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).getByRole('button', { name: date.split('-').reverse().join('/') }));
}

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2027-11-01T12:00:00Z'));
  vi.spyOn(api, 'listPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'getPublicAvailability').mockImplementation(async (id, range) => id === 1 ? { equipment_id: id, start_date: range!.start_date, end_date: range!.end_date, status: 'available', available: true } : { equipment_id: id, start_date: range!.start_date, end_date: range!.end_date, status: 'unavailable', available: false });
});
afterEach(() => { vi.useRealTimers(); });

describe('public catalogue', () => {
  it('restores a remembered result position only after the asynchronous cards have loaded', async () => {
    const path = '/catalogo?q=Aurora';
    vi.spyOn(window, 'scrollY', 'get').mockReturnValue(940);
    rememberCataloguePosition(path);
    const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => window.setTimeout(() => callback(0), 0));
    let finish!: (items: PublicEquipment[]) => void;
    const pending = new Promise<PublicEquipment[]>((resolve) => { finish = resolve; });
    vi.mocked(api.listPublicEquipment).mockReturnValue(pending);
    renderCatalogue(path);
    expect(scroll).not.toHaveBeenCalled();
    await act(async () => { finish(equipment); });
    await screen.findByRole('heading', { name: equipment[0]!.name });
    await waitFor(() => expect(scroll).toHaveBeenCalledExactlyOnceWith({ top: 940, left: 0, behavior: 'instant' }));
    const link = new URL(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' }).getAttribute('href')!, 'https://rentalab.invalid');
    expect(link.searchParams.get('catalogue')).toBe(path);
  });

  it('opens the selected model dates without leaving the catalogue or changing applied rental dates', async () => {
    vi.spyOn(api, 'getPublicReservationDates').mockResolvedValue({ equipment_id: 2, reservations: [{ start_date: '2027-11-01', end_date: '2027-11-04' }] });
    renderCatalogue('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    expect(api.getPublicReservationDates).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Ver fechas de 4 reservas de Micrófono Brisa' }));
    const region = await screen.findByRole('region', { name: 'Fechas de las reservas de Micrófono Brisa' });
    expect(await within(region).findByText('01/11/2027')).toBeInTheDocument();
    expect(within(region).getByText('04/11/2027')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?start_date=2027-11-10&end_date=2027-11-12');
    expect(screen.getByRole('link', { name: 'Ver Micrófono Brisa' })).toHaveAttribute('href', '/equipos/2?start_date=2027-11-10&end_date=2027-11-12');
    expect(api.getPublicReservationDates).toHaveBeenCalledExactlyOnceWith(2, expect.any(AbortSignal));
  });

  it('shows each model reservation count beside its action independently of today availability', async () => {
    renderCatalogue();
    await screen.findByText('No disponible hoy');
    for (const item of equipment) {
      const card = screen.getByRole('heading', { name: item.name }).closest('li')!;
      const count = within(card).getByText(`${item.active_reservations_count} reservas`);
      expect(count).toBeInTheDocument();
      expect(within(card).getByText('En curso y próximas')).toBeInTheDocument();
      expect(within(card).getByRole('link', { name: 'Ver equipo' }).parentElement).toContainElement(count);
    }
  });

  it('keeps the global count for selected dates and updates it when the catalogue is reloaded', async () => {
    vi.mocked(api.listPublicEquipment).mockResolvedValue([{ ...equipment[1]!, active_reservations_count: 1 }]);
    renderCatalogue('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('No disponible para tus fechas');
    expect(screen.getByText('1 reserva')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver equipo' })).toHaveAttribute('href', '/equipos/2?start_date=2027-11-10&end_date=2027-11-12');
    vi.mocked(api.listPublicEquipment).mockResolvedValue([{ ...equipment[1]!, active_reservations_count: 0 }]);
    fireEvent.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('0 reservas');
    expect(screen.queryByText('1 reserva')).not.toBeInTheDocument();
  });

  it('shows real green and red availability for today without applying dates to the search or product links', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T12:00:00Z'));
    renderCatalogue();
    expect(await screen.findByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Sonido' })).toBeInTheDocument();
    expect(screen.getByText('Disponible hoy').closest('p')).toHaveClass('is-available');
    expect(screen.getByText('No disponible hoy').closest('p')).toHaveClass('is-unavailable');
    expect(screen.queryByText('Selecciona fechas para ver disponibilidad')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(api.getPublicAvailability).toHaveBeenCalledTimes(2);
    for (const item of equipment) {
      expect(api.getPublicAvailability).toHaveBeenCalledWith(item.id, { start_date: '2026-10-15', end_date: '2026-10-16' }, expect.any(AbortSignal));
    }
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1');
  });

  it('immediately filters today without dates and restores all equipment when unchecked using the keyboard', async () => {
    renderCatalogue();
    await screen.findByText('No disponible hoy');
    const user = userEvent.setup();
    const checkbox = screen.getByRole('checkbox', { name: 'Solo disponibles' });
    checkbox.focus();
    await user.keyboard(' ');
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(checkbox).toBeChecked();
    expect(screen.getByText('Disponible hoy')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?available=1');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1?catalogue=%2Fcatalogo%3Favailable%3D1');
    await user.keyboard(' ');
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
  });

  it('restores a date-free available filter from the URL and preserves incomplete date drafts when toggled', async () => {
    renderCatalogue('/catalogo?available=1');
    await screen.findByText('Disponible hoy');
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
    chooseDate('inicio', '2027-11-10');
    const checkbox = screen.getByRole('checkbox', { name: 'Solo disponibles' });
    expect(checkbox).toBeChecked();
    fireEvent.click(checkbox);
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
  ])('uses the Madrid calendar day and exclusive following day at %s', async (now, today, tomorrow) => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(now));
    renderCatalogue();
    await screen.findByText('Disponible hoy');
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: today, end_date: tomorrow }, expect.any(AbortSignal));
  });

  it('checks the new day when returning to the catalogue after Madrid midnight', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T21:30:00Z'));
    renderCatalogue();
    await screen.findByText('Disponible hoy');
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2026-10-15', end_date: '2026-10-16' }, expect.any(AbortSignal));
    vi.mocked(api.getPublicAvailability).mockClear();
    vi.setSystemTime(new Date('2026-10-15T22:30:00Z'));
    fireEvent.focus(window);
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2026-10-16', end_date: '2026-10-17' }, expect.any(AbortSignal)));
    expect(await screen.findByText('Disponible hoy')).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
  });

  it('never marks equipment available when today could not be checked and retries the availability request', async () => {
    vi.mocked(api.getPublicAvailability).mockRejectedValue(new Error('No se pudo consultar la disponibilidad.'));
    renderCatalogue();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo consultar la disponibilidad.');
    expect(screen.queryByText('Disponible hoy')).not.toBeInTheDocument();
    expect(screen.queryByText('No disponible hoy')).not.toBeInTheDocument();
    vi.mocked(api.getPublicAvailability).mockImplementation(async (id, range) => ({ equipment_id: id, start_date: range!.start_date, end_date: range!.end_date, status: 'available', available: true }));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Volver a cargar' }));
    expect(await screen.findAllByText('Disponible hoy')).toHaveLength(2);
  });

  it('combines search and category via the public API without losing all-category options', async () => {
    vi.mocked(api.listPublicEquipment).mockImplementation(async (filters) => filters?.q || filters?.category ? [equipment[0]!] : equipment);
    renderCatalogue();
    const user = userEvent.setup();
    await screen.findByRole('option', { name: 'Sonido' });
    await user.type(screen.getByRole('searchbox', { name: 'Buscar equipo' }), 'Aurora');
    await user.selectOptions(screen.getByLabelText('Categoría'), 'Cámaras');
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await waitFor(() => expect(api.listPublicEquipment).toHaveBeenLastCalledWith({ q: 'Aurora', category: 'Cámaras' }, expect.any(AbortSignal)));
    expect(screen.getByRole('option', { name: 'Sonido' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
  });

  it('queries the selected calendar strings, filters only explicit available results and keeps dates in product links', async () => {
    renderCatalogue('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    const user = userEvent.setup();
    await screen.findByText('Disponible para tus fechas');
    expect(screen.getByText('No disponible para tus fechas').closest('p')).toHaveClass('is-unavailable');
    expect(screen.queryByText('Disponible hoy')).not.toBeInTheDocument();
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2027-11-10', end_date: '2027-11-12' }, expect.any(AbortSignal));
    await user.click(screen.getByRole('checkbox', { name: 'Solo disponibles' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(await screen.findByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(screen.queryByText(/avería|reserva #|cliente@/i)).not.toBeInTheDocument();
  });

  it('selects and clears calendar dates as drafts until the catalogue is consulted', async () => {
    renderCatalogue();
    const user = userEvent.setup();
    await screen.findByText('Disponible hoy');
    vi.mocked(api.getPublicAvailability).mockClear();
    chooseDate('inicio', '2027-11-10');
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Fechas del alquiler' })).getByRole('button', { name: '12/11/2027' }));
    expect(screen.queryByRole('dialog', { name: 'Fechas del alquiler' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: 12/11/2027' })).toHaveFocus();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', '/equipos/1');
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('Disponible para tus fechas');
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2027-11-10', end_date: '2027-11-12' }, expect.any(AbortSignal));
    vi.mocked(api.getPublicAvailability).mockClear();
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' }));
    await user.click(screen.getByRole('button', { name: 'Borrar fechas' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Solo disponibles' })).toBeEnabled();
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await screen.findByText('Disponible hoy');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2027-11-01', end_date: '2027-11-02' }, expect.any(AbortSignal));
  });

  it('rejects incomplete dates without replacing the checked availability for today', async () => {
    renderCatalogue();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.getPublicAvailability).mockClear();
    chooseDate('inicio', '2027-11-10');
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    expect(await screen.findByRole('alert')).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toHaveAttribute('aria-invalid', 'true');
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(screen.getByText('Disponible hoy').closest('p')).toHaveClass('is-available');
  });

  it('replaces a failed optional remote image with the supplied local alternative only once', async () => {
    renderCatalogue();
    const image = await screen.findByRole('img', { name: 'Micrófono Brisa' });
    fireEvent.error(image);
    const fallback = screen.getByRole('img', { name: 'Imagen de referencia para Micrófono Brisa' });
    expect(fallback).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    fireEvent.error(fallback);
    expect(fallback).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    const cameraCard = screen.getByRole('heading', { name: 'Cámara Aurora S4' }).closest('li');
    expect(within(cameraCard!).getByRole('img')).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
  });

  it('labels local example photographs and keeps the fallback when one fails', async () => {
    vi.mocked(api.listPublicEquipment).mockResolvedValue([{ ...equipment[0]!, image_url: '/api/public/images/demo-camera.jpg' }]);
    renderCatalogue();
    const image = await screen.findByRole('img', { name: 'Fotografía de ejemplo para Cámara Aurora S4' });
    expect(image).toHaveAttribute('src', '/api/public/images/demo-camera.jpg');
    expect(screen.getByText('Fotografía de ejemplo')).toBeInTheDocument();
    fireEvent.error(image);
    expect(screen.getByRole('img', { name: 'Imagen de referencia para Cámara Aurora S4' })).toHaveAttribute('src', '/api/public/images/equipment-placeholder.svg');
    expect(screen.queryByText('Fotografía de ejemplo')).not.toBeInTheDocument();
  });

  it('keeps results stable before the search delay and lets Enter apply immediately', async () => {
    vi.mocked(api.listPublicEquipment).mockImplementation(async (filters) => filters?.q ? [equipment[0]!] : equipment);
    renderCatalogue();
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    vi.mocked(api.listPublicEquipment).mockClear();
    const user = userEvent.setup();
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    await user.click(input);
    fireEvent.change(input, { target: { value: 'Aurora' } });
    expect(input).toHaveFocus();
    expect(input).toHaveValue('Aurora');
    expect(screen.getByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(api.listPublicEquipment).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument());
    expect(api.listPublicEquipment).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora');
  });

  it('keeps availability and product dates tied to the applied range until valid draft filters are submitted', async () => {
    renderCatalogue('/catalogo?q=Aurora&start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('Disponible para tus fechas');
    vi.mocked(api.listPublicEquipment).mockClear();
    vi.mocked(api.getPublicAvailability).mockClear();
    const user = userEvent.setup();
    chooseDate('inicio', '2027-11-20');
    await user.selectOptions(screen.getByLabelText('Categoría'), 'Cámaras');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(api.listPublicEquipment).not.toHaveBeenCalled();
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    expect(await screen.findByRole('alert')).toHaveFocus();
    expect(api.listPublicEquipment).not.toHaveBeenCalled();
    chooseDate('fin', '2027-11-22');
    await user.click(screen.getByRole('button', { name: 'Consultar catálogo' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-20&end_date=2027-11-22')));
    expect(api.listPublicEquipment).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: 'Cámaras' }, expect.any(AbortSignal));
    expect(api.getPublicAvailability).toHaveBeenCalledWith(1, { start_date: '2027-11-20', end_date: '2027-11-22' }, expect.any(AbortSignal));
  });

  it('restores fields with browser history and resets both applied filters and drafts when clearing an empty search', async () => {
    vi.mocked(api.listPublicEquipment).mockImplementation(async (filters) => filters?.q === 'Nada' ? [] : equipment);
    renderCatalogue();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Micrófono Brisa' });
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    await user.click(input);
    fireEvent.change(input, { target: { value: 'Aurora' } });
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora'));
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    chooseDate('inicio', '2027-11-20');
    await user.click(screen.getByRole('button', { name: 'Atrás' }));
    expect(input).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Adelante' }));
    expect(input).toHaveValue('Aurora');
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir fecha' })).toBeInTheDocument();
    await user.click(input);
    fireEvent.change(input, { target: { value: 'Nada' } });
    await user.keyboard('{Enter}');
    await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' });
    chooseDate('inicio', '2027-11-20');
    await user.click(screen.getByRole('button', { name: 'Ver todo el catálogo' }));
    expect(input).toHaveValue('');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
  });

  it('clears an unsubmitted draft even when the unfiltered catalogue is empty', async () => {
    vi.mocked(api.listPublicEquipment).mockResolvedValue([]);
    renderCatalogue();
    await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' });
    const user = userEvent.setup();
    await user.type(screen.getByRole('searchbox', { name: 'Buscar equipo' }), 'Aurora');
    await user.click(screen.getByRole('button', { name: 'Ver todo el catálogo' }));
    expect(screen.getByRole('searchbox', { name: 'Buscar equipo' })).toHaveValue('');
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
    expect(await screen.findByRole('heading', { name: 'No encontramos equipos para esta búsqueda' })).toBeInTheDocument();
  });

  it('automatically searches once after 150 ms and keeps cards mounted and focus while waiting for the network', async () => {
    let finish!: (value: PublicEquipment[]) => void;
    vi.mocked(api.listPublicEquipment).mockImplementation((filters) => filters?.q ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve(equipment));
    renderCatalogue();
    const camera = await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listPublicEquipment).mockClear();
    vi.useFakeTimers();
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    input.focus();
    for (let length = 1; length <= 'Aurora'.length; length++) fireEvent.change(input, { target: { value: 'Aurora'.slice(0, length) } });
    await act(() => vi.advanceTimersByTimeAsync(149));
    expect(api.listPublicEquipment).not.toHaveBeenCalled();
    expect(input).toHaveFocus();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(api.listPublicEquipment).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBe(camera);
    expect(screen.getByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Explora el catálogo' })).toHaveAttribute('aria-busy', 'true');
    expect(input).toHaveFocus();
    await act(async () => { finish([equipment[0]!]); });
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBe(camera);
    expect(screen.queryByRole('heading', { name: 'Micrófono Brisa' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toHaveTextContent('?q=Aurora');
    expect(input).toHaveFocus();
  });

  it('aborts an older search, ignores its late response and automatically restores results when clearing the input', async () => {
    let finishOld!: (value: PublicEquipment[]) => void;
    vi.mocked(api.listPublicEquipment).mockImplementation((filters) => filters?.q === 'Aurora' ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve(filters?.q ? [equipment[1]!] : equipment));
    renderCatalogue();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listPublicEquipment).mockClear();
    vi.useFakeTimers();
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    fireEvent.change(input, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    const oldSignal = vi.mocked(api.listPublicEquipment).mock.calls[0]![1]!;
    fireEvent.change(input, { target: { value: 'Brisa' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(oldSignal.aborted).toBe(true);
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    await act(async () => { finishOld([equipment[0]!]); });
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    expect(input).toHaveValue('Brisa');
    fireEvent.change(input, { target: { value: '' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByLabelText('Consulta aplicada')).toBeEmptyDOMElement();
  });

  it('preserves category and incomplete date drafts when live search changes only the query URL', async () => {
    renderCatalogue('/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    await screen.findByText('Disponible para tus fechas');
    vi.mocked(api.listPublicEquipment).mockClear();
    vi.useFakeTimers();
    chooseDate('inicio', '2027-11-20');
    fireEvent.change(screen.getByLabelText('Categoría'), { target: { value: 'Cámaras' } });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar equipo' }), { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(api.listPublicEquipment).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 20/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de fin: Elegir fecha' })).toBeInTheDocument();
    expect(screen.getByLabelText('Categoría')).toHaveValue('Cámaras');
    expect(screen.getByRole('link', { name: 'Ver Cámara Aurora S4' })).toHaveAttribute('href', expect.stringContaining('/equipos/1?start_date=2027-11-10&end_date=2027-11-12'));
    expect(screen.getByLabelText('Consulta aplicada')).not.toHaveTextContent('category=');
  });

  it('does not search during input composition or repeat the request after an immediate Enter', async () => {
    renderCatalogue();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.mocked(api.listPublicEquipment).mockClear();
    vi.useFakeTimers();
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(api.listPublicEquipment).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
    fireEvent.submit(screen.getByRole('form', { name: 'Buscar en el catálogo' }));
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(api.listPublicEquipment).toHaveBeenCalledExactlyOnceWith({ q: 'Aurora', category: '' }, expect.any(AbortSignal));
  });

  it('shows an asynchronous error without taking focus and retries the current search', async () => {
    vi.mocked(api.listPublicEquipment).mockImplementation(async (filters) => {
      if (filters?.q) throw new Error('No se pudo actualizar el catálogo.');
      return equipment;
    });
    renderCatalogue();
    await screen.findByRole('heading', { name: 'Cámara Aurora S4' });
    vi.useFakeTimers();
    const input = screen.getByRole('searchbox', { name: 'Buscar equipo' });
    input.focus();
    fireEvent.change(input, { target: { value: 'Aurora' } });
    await act(() => vi.advanceTimersByTimeAsync(150));
    expect(screen.getByRole('alert')).toHaveTextContent('No se pudo actualizar el catálogo.');
    expect(input).toHaveFocus();
    expect(screen.queryByRole('heading', { name: 'Cámara Aurora S4' })).not.toBeInTheDocument();
    vi.mocked(api.listPublicEquipment).mockResolvedValue([equipment[0]!]);
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar' }));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Buscar equipo' })).toHaveValue('Aurora');
  });
});
