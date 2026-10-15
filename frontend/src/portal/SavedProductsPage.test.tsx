import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, type AuthSession, type CustomerReservation, type PublicEquipment } from '../api/client';
import { AuthContext } from '../auth/context';
import { allowedDestination, postLoginDestination } from '../auth/destinations';
import { SaveProductButton } from './SaveProductButton';
import SavedProductsPage from './SavedProductsPage';
import { SavedProductsProvider } from './SavedProductsProvider';
import { useSavedProducts } from './savedProductsContext';

const dates = { start_date: '2027-11-17', end_date: '2027-11-20' };
const session: AuthSession = { authenticated: true, username: 'ana@example.test', expires_at: '2027-12-01T12:00:00Z', role: 'customer', user: { id: 4, name: 'Ana', email: 'ana@example.test', role: 'customer', active: true } };
const products: PublicEquipment[] = [
  { id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: '', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
  { id: 2, name: 'Micrófono Brisa', category: 'Sonido', public_description: '', technical_specs: {}, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0 },
];

function Count() { const saved = useSavedProducts(); return <output aria-label="Guardados">{saved.ids.length}</output>; }
function renderList(path = '/mi-lista?start_date=2027-11-17&end_date=2027-11-20') {
  return render(<AuthContext.Provider value={{ session, checking: false, checkError: null, expired: false, login: vi.fn(), logout: vi.fn(), checkSession: vi.fn() }}><MemoryRouter initialEntries={[path]}><SavedProductsProvider customer><Count /><SavedProductsPage /></SavedProductsProvider></MemoryRouter></AuthContext.Provider>);
}
function confirmButton() { return screen.getByRole('button', { name: 'Reservar 2 equipos a la vez' }); }

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2027-11-01T12:00:00Z'));
  vi.spyOn(api, 'listSavedProducts').mockResolvedValue({ equipment_ids: [1, 2] });
  vi.spyOn(api, 'getPublicEquipment').mockImplementation(async (id) => products.find((item) => item.id === id)!);
  vi.spyOn(api, 'getPublicAvailability').mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range!, available: true, status: 'available' }));
  vi.spyOn(api, 'getPublicAvailabilityCalendar').mockImplementation(async (equipment_id, range) => ({ equipment_id, start_date: range.start_date, end_date: range.end_date, can_book: true, occupied_ranges: [], unavailable_end_dates: [] }));
  vi.spyOn(api, 'removeSavedProduct').mockResolvedValue({ equipment_ids: [2] });
  vi.spyOn(api, 'createMyReservationsBatch').mockImplementation(async (input) => input.equipment_ids.map((equipment_id, index) => ({ equipment_id, id: 41 + index, start_date: input.start_date, end_date: input.end_date, status: 'confirmed' })));
});
afterEach(() => { vi.useRealTimers(); });

describe('Mi lista and joint reservation', () => {
  it('recovers a one-product batch after reload and retries the same intent despite full availability', async () => {
    vi.mocked(api.createMyReservationsBatch).mockRejectedValueOnce(new ApiError('Lost response', 0));
    const first = renderList();
    const user = userEvent.setup();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No hemos podido comprobar si se confirmó la reserva conjunta.');
    const key = vi.mocked(api.createMyReservationsBatch).mock.calls[0]![1];
    first.unmount();
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range!, available: false, status: 'unavailable' }));
    renderList();
    const retry = await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    expect(retry).toBeEnabled();
    expect(await screen.findByRole('checkbox', { name: 'Seleccionar Cámara Aurora S4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).not.toBeChecked();
    expect(api.createMyReservationsBatch).toHaveBeenCalledTimes(1);
    await user.click(retry);
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.createMyReservationsBatch).toHaveBeenNthCalledWith(2, { equipment_ids: [1], ...dates }, key);
  });

  it('reuses a multi-product batch key on server failure and creates a new key for changed selection', async () => {
    vi.mocked(api.createMyReservationsBatch).mockRejectedValueOnce(new ApiError('Lost response', 500));
    renderList();
    const user = userEvent.setup();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    await user.click(confirmButton());
    const key = vi.mocked(api.createMyReservationsBatch).mock.calls[0]![1];
    await user.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(api.createMyReservationsBatch).toHaveBeenNthCalledWith(2, { equipment_ids: [1, 2], ...dates }, key);
    await user.click(await screen.findByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(vi.mocked(api.createMyReservationsBatch).mock.calls[2]![1]).not.toBe(key);
  });

  it('keeps completed batches across asynchronous saved-list hydration and allows a deliberate additional operation', async () => {
    const first = renderList();
    const user = userEvent.setup();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    await user.click(confirmButton());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    const key = vi.mocked(api.createMyReservationsBatch).mock.calls[0]![1];
    first.unmount();
    renderList();
    await screen.findByRole('region', { name: 'Reserva conjunta registrada' });
    expect(screen.queryByRole('button', { name: 'Reservar 2 equipos a la vez' })).not.toBeInTheDocument();
    expect(api.createMyReservationsBatch).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    await user.click(confirmButton());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(vi.mocked(api.createMyReservationsBatch).mock.calls[1]![1]).not.toBe(key);
  });

  it('recovers original batch identifiers when active canonical products change after a lost response', async () => {
    vi.mocked(api.listSavedProducts).mockResolvedValue({ equipment_ids: [1] });
    vi.mocked(api.createMyReservationsBatch).mockRejectedValueOnce(new ApiError('Lost response', 0));
    const first = renderList();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.createMyReservationsBatch).mock.calls[0]![1];
    first.unmount();
    vi.mocked(api.listSavedProducts).mockResolvedValue({ equipment_ids: [2] });
    renderList();
    expect(await screen.findByText('Tu lista ha cambiado desde la reserva anterior. Consulta o recupera esa operación antes de preparar otra.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.createMyReservationsBatch).toHaveBeenNthCalledWith(2, { equipment_ids: [1], ...dates }, key);
    await user.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.createMyReservationsBatch).toHaveBeenNthCalledWith(3, { equipment_ids: [2], ...dates }, expect.any(String));
    expect(vi.mocked(api.createMyReservationsBatch).mock.calls[2]![1]).not.toBe(key);
  });

  it('defaults all products to selected, shows individual dates and confirms once while preserving favorites', async () => {
    renderList();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Cámara Aurora S4' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).toBeChecked();
    expect(screen.getAllByText('Disponible para todo el periodo')).toHaveLength(2);
    expect(screen.getByText('Todos disponibles del 17/11/2027 al 20/11/2027.')).toBeInTheDocument();
    fireEvent.click(confirmButton());
    await screen.findByRole('heading', { name: '2 reservas confirmadas' });
    expect(api.createMyReservationsBatch).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1, 2], ...dates }, expect.any(String));
    expect(api.removeSavedProduct).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('2');
    await waitFor(() => expect(screen.getByRole('heading', { name: '2 reservas confirmadas' })).toHaveFocus());
    expect(screen.getByRole('link', { name: 'Reserva #41 · Cámara Aurora S4' })).toHaveAttribute('href', '/mis-reservas/41');
    expect(screen.getByRole('link', { name: 'Ver mis reservas' })).toHaveAttribute('href', '/mis-reservas');
  });

  it('compares the shared calendar intersection and permits a selected available subset', async () => {
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => equipment_id === 1 ? { equipment_id, ...range!, available: true, status: 'available' } : { equipment_id, ...range!, available: false, status: 'unavailable' });
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, range) => ({ equipment_id, start_date: range.start_date, end_date: range.end_date, can_book: true, occupied_ranges: equipment_id === 2 ? [{ start_date: '2027-11-18', end_date: '2027-11-19' }] : [], unavailable_end_dates: equipment_id === 2 ? ['2027-11-20'] : [] }));
    renderList();
    expect(await screen.findByText('No disponible para todo el periodo')).toBeInTheDocument();
    await waitFor(() => expect(confirmButton()).toBeDisabled());
    expect(screen.getByRole('button', { name: /^18\/11\/2027: Ocupado/ })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.createMyReservationsBatch).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1], ...dates }, expect.any(String));
  });

  it('labels just-confirmed models as reserved after availability refresh while preserving unselected status', async () => {
    let confirmed = false;
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => equipment_id === 1 && !confirmed
      ? { equipment_id, ...range!, available: true, status: 'available' }
      : { equipment_id, ...range!, available: false, status: 'unavailable' });
    vi.mocked(api.createMyReservationsBatch).mockImplementation(async (input) => {
      confirmed = true;
      return [{ equipment_id: 99, id: 41, start_date: input.start_date, end_date: input.end_date, status: 'confirmed' }];
    });
    renderList();
    await screen.findByText('No disponible para todo el periodo');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(4));
    expect(await screen.findByText('Reservado del 17/11/2027 al 20/11/2027')).toHaveClass('is-available');
    expect(screen.getAllByText('No disponible para todo el periodo')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Reserva #41 · Cámara Aurora S4' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    expect(screen.queryByText('Reservado del 17/11/2027 al 20/11/2027')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('No disponible para todo el periodo')).toHaveLength(2));
  });

  it('rejects double confirmation and locks dates and product selection while the atomic request is pending', async () => {
    let resolve: ((value: CustomerReservation[]) => void) | undefined;
    vi.mocked(api.createMyReservationsBatch).mockImplementation(() => new Promise((done) => { resolve = done; }));
    renderList();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    const button = confirmButton(); fireEvent.click(button); fireEvent.click(button);
    expect(screen.getByRole('button', { name: 'Confirmando todos los equipos…' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toBeDisabled();
    expect(api.createMyReservationsBatch).toHaveBeenCalledTimes(1);
    await act(async () => resolve?.([1, 2].map((equipment_id, index) => ({ equipment_id, id: 41 + index, ...dates, status: 'confirmed' }))));
    expect(await screen.findByRole('heading', { name: '2 reservas confirmadas' })).toBeInTheDocument();
  });

  it('allows an available subset when an excluded product availability request fails', async () => {
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => {
      if (equipment_id === 2) throw new ApiError('No se pudo conectar', 0);
      return { equipment_id, ...range!, available: true, status: 'available' };
    });
    renderList();
    await screen.findByRole('button', { name: 'Reintentar disponibilidad' });
    expect(confirmButton()).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar Micrófono Brisa' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' }));
    await screen.findByRole('heading', { name: '1 reserva confirmada' });
    expect(api.createMyReservationsBatch).toHaveBeenCalledExactlyOnceWith({ equipment_ids: [1], ...dates }, expect.any(String));
  });

  it('checks every selected model before offering a return in a later month', async () => {
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => equipment_id === 2 && range?.end_date === '2027-12-01'
      ? { equipment_id, ...range!, available: false, status: 'unavailable' }
      : { equipment_id, ...range!, available: true, status: 'available' });
    renderList(); await waitFor(() => expect(confirmButton()).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Fecha de devolución: 20/11/2027' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledWith(2, { start_date: '2027-11-17', end_date: '2027-12-01' }, expect.any(AbortSignal)));
    expect(screen.getByRole('button', { name: /^02\/12\/2027: Disponible/ })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('button', { name: /^02\/12\/2027: Disponible/ }));
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 20/11/2027' })).toBeInTheDocument();
  });

  it('keeps all favorites and rechecks both products after a 409 without showing partial success', async () => {
    vi.mocked(api.createMyReservationsBatch).mockRejectedValue(new ApiError('Ocupado', 409));
    renderList(); await waitFor(() => expect(confirmButton()).toBeEnabled());
    fireEvent.click(confirmButton());
    expect(await screen.findByText(/La disponibilidad ha cambiado\. No se ha reservado ningún equipo/)).toBeInTheDocument();
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(4));
    expect(screen.queryByRole('heading', { name: '2 reservas confirmadas' })).not.toBeInTheDocument();
    expect(api.createMyReservationsBatch).toHaveBeenCalledTimes(1);
    expect(api.removeSavedProduct).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('2');
  });

  it('retains unavailable saved IDs, blocks confirmation, and lets the customer remove one', async () => {
    vi.mocked(api.getPublicEquipment).mockImplementation(async (id) => { if (id === 1) throw new ApiError('No existe', 404); return products[1]!; });
    renderList();
    expect(await screen.findByText('Este equipo ya no está en el catálogo. Puedes quitarlo de tu lista.')).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Equipo #1 de mi lista' }));
    await waitFor(() => expect(screen.getByLabelText('Guardados')).toHaveTextContent('1'));
    expect(api.removeSavedProduct).toHaveBeenCalledExactlyOnceWith(1);
    expect(screen.queryByRole('heading', { name: 'Equipo #1' })).not.toBeInTheDocument();
  });

  it('offers separate per-product calendars without altering the shared selected period', async () => {
    renderList(); await waitFor(() => expect(confirmButton()).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Ver calendario de Cámara Aurora S4' }));
    const calendar = await screen.findByRole('region', { name: 'Calendario de Cámara Aurora S4' });
    expect(within(calendar).getByText('noviembre de 2027')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
    expect(api.createMyReservationsBatch).not.toHaveBeenCalled();
  });

  it('refreshes canonical saved models when a representative unit disappears', async () => {
    vi.mocked(api.listSavedProducts).mockResolvedValueOnce({ equipment_ids: [1] }).mockResolvedValueOnce({ equipment_ids: [2] });
    vi.mocked(api.getPublicEquipment).mockImplementation(async (id) => { if (id === 1) throw new ApiError('No existe', 404); return products[1]!; });
    renderList();
    await screen.findByRole('heading', { name: 'Equipo #1' });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar mi lista' }));
    expect(await screen.findByRole('heading', { name: 'Micrófono Brisa' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reservar 1 equipo a la vez' })).toBeEnabled());
    expect(api.listSavedProducts).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('heading', { name: 'Equipo #1' })).not.toBeInTheDocument();
  });

  it('shows an empty list and a retryable fetch failure', async () => {
    vi.mocked(api.listSavedProducts).mockRejectedValueOnce(new ApiError('Sin conexión', 0)).mockResolvedValueOnce({ equipment_ids: [] });
    renderList();
    expect(await screen.findByRole('alert')).toHaveTextContent('Sin conexión');
    fireEvent.click(screen.getByRole('button', { name: 'Volver a cargar mi lista' }));
    expect(await screen.findByRole('heading', { name: 'Tu próximo proyecto empieza aquí' })).toBeInTheDocument();
    expect(api.createMyReservationsBatch).not.toHaveBeenCalled();
  });

  it('fails closed on a calendar or availability failure and preserves the selection for retry', async () => {
    vi.mocked(api.getPublicAvailability).mockRejectedValue(new ApiError('Sin conexión', 0));
    renderList();
    expect(await screen.findByRole('button', { name: 'Reintentar disponibilidad' })).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
    vi.mocked(api.getPublicAvailability).mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range!, available: true, status: 'available' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar disponibilidad' }));
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('never confirms an invalid or past period', async () => {
    renderList('/mi-lista?start_date=2027-10-17&end_date=2027-10-20');
    expect(await screen.findByText('Elige hoy o una fecha posterior para reservar.')).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
    expect(api.createMyReservationsBatch).not.toHaveBeenCalled();
  });

  it('ignores a previous period response after the customer changes shared dates', async () => {
    let finish: ((value: Awaited<ReturnType<typeof api.getPublicAvailability>>) => void) | undefined;
    vi.mocked(api.getPublicAvailability).mockImplementation((equipment_id, range) => equipment_id === 1 ? new Promise((done) => { finish = done; }) : Promise.resolve({ equipment_id, ...range!, available: true, status: 'available' }));
    renderList();
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: /^21\/11\/2027: Disponible/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /^21\/11\/2027: Disponible/ }));
    await act(async () => finish?.({ equipment_id: 1, ...dates, available: true, status: 'available' }));
    expect(confirmButton()).toBeDisabled();
    expect(api.createMyReservationsBatch).not.toHaveBeenCalled();
  });
});

describe('save controls and account boundaries', () => {
  it('persists saving and removing through the server, updates shared count, and survives a fresh provider', async () => {
    vi.mocked(api.listSavedProducts).mockResolvedValueOnce({ equipment_ids: [] }).mockResolvedValueOnce({ equipment_ids: [1] });
    vi.spyOn(api, 'saveProduct').mockResolvedValue({ equipment_ids: [1] });
    const view = render(<MemoryRouter><SavedProductsProvider customer><Count /><SaveProductButton id={1} name="Cámara Aurora S4" /></SavedProductsProvider></MemoryRouter>);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar Cámara Aurora S4 en mi lista' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Guardar Cámara Aurora S4 en mi lista' }));
    expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('1');
    expect(api.saveProduct).toHaveBeenCalledExactlyOnceWith(1);
    view.unmount();
    render(<MemoryRouter><SavedProductsProvider customer><SaveProductButton id={1} name="Cámara Aurora S4" /></SavedProductsProvider></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Quitar Cámara Aurora S4 de mi lista' })).toBeEnabled());
  });

  it('preserves dates in guest login destinations and allows returning to Mi lista safely', () => {
    render(<MemoryRouter initialEntries={['/equipos/1?start_date=2027-11-17&end_date=2027-11-20']}><SaveProductButton id={1} name="Cámara Aurora S4" /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Acceder para guardar Cámara Aurora S4 en mi lista' })).toHaveAttribute('href', '/acceso?next=%2Fequipos%2F1%3Fstart_date%3D2027-11-17%26end_date%3D2027-11-20');
    expect(allowedDestination('/mi-lista?start_date=2027-11-17&end_date=2027-11-20')).toBe('/mi-lista?start_date=2027-11-17&end_date=2027-11-20');
    expect(postLoginDestination('customer', '/mi-lista')).toBe('/mi-lista');
    expect(allowedDestination('//evil.test/mi-lista')).toBeNull();
    expect(api.listSavedProducts).not.toHaveBeenCalled();
  });

  it('prevents a previous account response from changing the next account list', async () => {
    let finish: ((value: { equipment_ids: number[] }) => void) | undefined;
    vi.mocked(api.listSavedProducts).mockImplementationOnce(() => new Promise((done) => { finish = done; })).mockResolvedValueOnce({ equipment_ids: [2] });
    const view = render(<SavedProductsProvider key="customer-1" customer><Count /></SavedProductsProvider>);
    await waitFor(() => expect(api.listSavedProducts).toHaveBeenCalledTimes(1));
    view.rerender(<SavedProductsProvider key="customer-2" customer><Count /></SavedProductsProvider>);
    await waitFor(() => expect(screen.getByLabelText('Guardados')).toHaveTextContent('1'));
    await act(async () => finish?.({ equipment_ids: [1, 2] }));
    expect(screen.getByLabelText('Guardados')).toHaveTextContent('1');
  });
});
