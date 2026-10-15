import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, type AuthSession, type CustomerReservation, type PublicAvailability, type PublicEquipment } from '../api/client';
import { AuthContext } from '../auth/context';
import { formatDate } from '../lib/dates';
import { todayInMadrid } from './dateRange';
import { ProductPage } from './ProductPage';
import { readReservationAttempt, reservationScope } from './reservationAttempt';

const equipment: PublicEquipment = {
  id: 1, name: 'Cámara Aurora S4', category: 'Cámaras', public_description: 'Para entrevistas en estudio.',
  technical_specs: { Resolución: '4K UHD', Conexiones: 'HDMI y USB-C' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0,
};
const session: AuthSession = {
  authenticated: true, username: 'ana@example.test', expires_at: '2026-11-30T12:00:00Z', role: 'customer',
  user: { id: 4, name: 'Ana', email: 'ana@example.test', role: 'customer', active: true },
};
const range = { start_date: '2027-11-10', end_date: '2027-11-12' };
const available: PublicAvailability = { equipment_id: 1, ...range, available: true, status: 'available' };

function Location() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname}{location.search}</p>;
}

function renderProduct(user: AuthSession | null = session, path = '/equipos/1?start_date=2027-11-10&end_date=2027-11-12') {
  return render(<AuthContext.Provider value={{ session: user, checking: false, checkError: null, expired: false, login: vi.fn(), logout: vi.fn(), checkSession: vi.fn() }}><MemoryRouter initialEntries={[path]}><Location /><Routes><Route path="/equipos/:id" element={<ProductPage />} /><Route path="/acceso" element={<h1>Accede a tu cuenta</h1>} /></Routes></MemoryRouter></AuthContext.Provider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  vi.spyOn(api, 'getPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'getPublicAvailability').mockImplementation(async (equipment_id, dates) => ({ equipment_id, ...dates, available: true, status: 'available' }));
  vi.spyOn(api, 'getPublicAvailabilityCalendar').mockImplementation(async (equipment_id, dates) => ({ equipment_id, ...dates, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'createMyReservation').mockImplementation(async (reservation) => ({ id: 42, ...reservation, status: 'confirmed' }));
});

describe('public product and explicit reservation', () => {
  it('retries an uncertain confirmation with the same key even when the interval is now occupied', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Lost response', 0));
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No hemos podido comprobar si se confirmó.');
    const key = vi.mocked(api.createMyReservation).mock.calls[0]![1];
    expect(key).toMatch(/^[0-9a-f-]{36}$/i);
    vi.mocked(api.getPublicAvailability).mockResolvedValue({ ...available, available: false, status: 'unavailable' });
    await user.click(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.createMyReservation).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...range }, key);
  });

  it('restores an uncertain attempt after remount and delayed session resolution without automatically submitting', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Lost response', 0));
    const first = renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.createMyReservation).mock.calls[0]![1];
    first.unmount();
    vi.mocked(api.getPublicAvailability).mockResolvedValue({ ...available, available: false, status: 'unavailable' });
    const value = { session: null as AuthSession | null, checking: true, checkError: null, expired: false, login: vi.fn(), logout: vi.fn(), checkSession: vi.fn() };
    const children = <MemoryRouter initialEntries={['/equipos/1?start_date=2027-11-10&end_date=2027-11-12']}><Routes><Route path="/equipos/:id" element={<ProductPage />} /></Routes></MemoryRouter>;
    const second = render(<AuthContext.Provider value={value}>{children}</AuthContext.Provider>);
    await screen.findByRole('heading', { name: equipment.name });
    second.rerender(<AuthContext.Provider value={{ ...value, session, checking: false }}>{children}</AuthContext.Provider>);
    const retry = await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    expect(retry).toBeEnabled();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    await user.click(retry);
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(api.createMyReservation).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...range }, key);
  });

  it('retains a completed operation after reload and rotates its key only for an explicit further reservation', async () => {
    const first = renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    const key = vi.mocked(api.createMyReservation).mock.calls[0]![1];
    first.unmount();
    renderProduct();
    await screen.findByRole('region', { name: 'Reserva registrada' });
    expect(screen.queryByRole('button', { name: 'Confirmar reserva' })).not.toBeInTheDocument();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Preparar otra reserva' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.createMyReservation).mock.calls[1]![1]).not.toBe(key);
  });

  it('creates separate operation keys for another account and for deliberately changed dates', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Lost response', 0));
    const first = renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const firstKey = vi.mocked(api.createMyReservation).mock.calls[0]![1];
    first.unmount();
    const second = renderProduct({ ...session, user: { ...session.user!, id: 9 } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.createMyReservation).mock.calls[1]![1]).not.toBe(firstKey);
    second.unmount();
    renderProduct();
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    await user.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await user.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(vi.mocked(api.createMyReservation).mock.calls[2]![1]).not.toBe(firstKey);
    expect(readReservationAttempt(reservationScope(4, { equipment_id: 1, ...range }))?.key).toBe(firstKey);
  });

  it('preserves the original uncertain intent through a date round trip', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Lost response', 0));
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' });
    const key = vi.mocked(api.createMyReservation).mock.calls[0]![1];
    await user.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await user.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Fecha de devolución: 14/11/2027' }));
    await user.click(await screen.findByRole('button', { name: '12/11/2027: Disponible' }));
    await user.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    await screen.findByRole('heading', { name: 'Reserva #42' });
    expect(api.createMyReservation).toHaveBeenNthCalledWith(2, { equipment_id: 1, ...range }, key);
  });

  it('shows the actual cancelled state returned by an idempotent replay', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Lost response', 500))
      .mockResolvedValueOnce({ id: 42, equipment_id: 1, ...range, status: 'cancelled' });
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    await user.click(await screen.findByRole('button', { name: 'Volver a confirmar de forma segura' }));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(screen.queryByText('Tu reserva se ha confirmado.')).not.toBeInTheDocument();
  });

  it('keeps catalogue filters while returning with changed product dates and rejects external return destinations', async () => {
    const catalogue = '/catalogo?q=Aurora&category=C%C3%A1maras&available=1';
    const first = renderProduct(session, `/equipos/1?start_date=2027-11-10&end_date=2027-11-12&catalogue=${encodeURIComponent(catalogue)}`);
    await screen.findByRole('heading', { name: equipment.name });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await user.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    const back = new URL(screen.getByRole('link', { name: 'Volver al catálogo' }).getAttribute('href')!, 'https://rentalab.invalid');
    expect(Object.fromEntries(back.searchParams)).toEqual({ start_date: range.start_date, end_date: '2027-11-14', q: 'Aurora', category: 'Cámaras', available: '1' });
    first.unmount();
    renderProduct(session, `/equipos/1?start_date=2027-11-10&end_date=2027-11-12&catalogue=${encodeURIComponent('https://evil.test')}`);
    expect(await screen.findByRole('link', { name: 'Volver al catálogo' })).toHaveAttribute('href', '/catalogo?start_date=2027-11-10&end_date=2027-11-12');
  });

  it('preserves equipment and dates in the allowed login destination without creating a reservation', async () => {
    renderProduct(null);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Acceder para reservar' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Acceder para reservar' }));
    await screen.findByRole('heading', { name: 'Accede a tu cuenta' });
    const destination = new URLSearchParams(screen.getByTestId('location').textContent?.split('?')[1]).get('next');
    expect(destination).toBe('/equipos/1?start_date=2027-11-10&end_date=2027-11-12');
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('requires a click after returning with a session and shows reference, status and detail link', async () => {
    renderProduct();
    await screen.findByText('Disponible del 10/11/2027 al 12/11/2027.');
    expect(api.createMyReservation).not.toHaveBeenCalled();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(screen.getByText('Confirmada')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/42');
    expect(api.createMyReservation).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...range }, expect.any(String));
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(2));
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(2);
  });

  it('confirms a reservation assigned to a sibling unit while retaining one public product presentation', async () => {
    vi.mocked(api.createMyReservation).mockResolvedValue({ id: 43, equipment_id: 2, ...range, status: 'confirmed' });
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #43' })).toHaveFocus();
    expect(screen.getByRole('heading', { name: 'Cámara Aurora S4' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/43');
    expect(api.createMyReservation).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...range }, expect.any(String));
    expect(screen.queryByText(/unidades|equipo #2/i)).not.toBeInTheDocument();
  });

  it('freezes the selected dates while confirming and prevents a second submission', async () => {
    let finish!: (reservation: CustomerReservation) => void;
    vi.mocked(api.createMyReservation).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.dblClick(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '14/11/2027: Disponible' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirmando reserva…' })).toBeDisabled();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ id: 42, equipment_id: 1, ...range, status: 'confirmed' }); });
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
  });

  it('keeps dates and focuses a conflict, automatically refreshes the calendar and allows different dates', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('El equipo no está disponible.', 409));
    vi.mocked(api.getPublicAvailability).mockResolvedValueOnce(available).mockResolvedValue({ ...available, status: 'unavailable', available: false });
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValueOnce({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true })
      .mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [range], can_book: true });
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('La disponibilidad ha cambiado');
    expect(alert).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(2));
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole('cell', { name: '10/11/2027: Ocupado' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Reserva #42' })).not.toBeInTheDocument();
    vi.mocked(api.getPublicAvailability).mockResolvedValue({ ...available, start_date: '2027-11-12', end_date: '2027-11-14', available: true, status: 'available' });
    await user.click(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' }));
    await user.click(screen.getByRole('button', { name: /^12\/11\/2027: Disponible/ }));
    await user.click(screen.getByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.createMyReservation).toHaveBeenCalledTimes(2);
  });

  it('ignores an old availability result after the selected date changes', async () => {
    let resolveOld!: (value: PublicAvailability) => void;
    let resolveNew!: (value: PublicAvailability) => void;
    vi.mocked(api.getPublicAvailability).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; })).mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve; }));
    renderProduct();
    await screen.findByRole('heading', { name: equipment.name });
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(1));
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' }));
    await user.click(await screen.findByRole('button', { name: '14/11/2027: Disponible' }));
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(2));
    await act(async () => { resolveOld(available); });
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    await act(async () => { resolveNew({ equipment_id: 1, start_date: range.start_date, end_date: '2027-11-14', available: false, status: 'unavailable' }); });
    expect(await screen.findByText('No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.')).toBeInTheDocument();
  });

  it('shows occupancy before choosing dates and automatically checks a calendar selection', async () => {
    const month = todayInMadrid().slice(0, 7);
    const nextMonthDate = new Date(`${month}-01T12:00:00Z`);
    nextMonthDate.setUTCMonth(nextMonthDate.getUTCMonth() + 1);
    const nextMonth = nextMonthDate.toISOString().slice(0, 7);
    const selected = { start_date: `${nextMonth}-10`, end_date: `${nextMonth}-12` };
    vi.mocked(api.getPublicAvailabilityCalendar).mockImplementation(async (equipment_id, dates) => ({
      equipment_id, ...dates, occupied_ranges: [{ start_date: `${dates.start_date.slice(0, 7)}-06`, end_date: `${dates.start_date.slice(0, 7)}-08` }], can_book: true,
    }));
    renderProduct(session, '/equipos/1');
    const user = userEvent.setup();
    expect(await screen.findByRole('cell', { name: `${formatDate(`${month}-06`)}: Ocupado` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Consultar disponibilidad' })).not.toBeInTheDocument();
    expect(screen.queryByText(/selecciona.*para conocer la disponibilidad/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(api.createMyReservation).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    await user.click(await screen.findByRole('button', { name: `${formatDate(selected.start_date)}: Disponible` }));
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: `${formatDate(selected.end_date)}: Disponible` }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(api.getPublicAvailability).toHaveBeenCalledExactlyOnceWith(1, selected, expect.anything());
    expect(screen.getByTestId('location')).toHaveTextContent(`start_date=${selected.start_date}&end_date=${selected.end_date}`);
    expect(api.createMyReservation).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toBeInTheDocument();
    expect(api.createMyReservation).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...selected }, expect.any(String));
  });

  it('shows an inverted URL range error without requesting availability', async () => {
    renderProduct(session, '/equipos/1?start_date=2027-11-12&end_date=2027-11-10');
    expect(await screen.findByText('La fecha de fin debe ser posterior al inicio.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.getPublicAvailability).not.toHaveBeenCalled();
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('clears the selected dates and the previous availability when changing dates', async () => {
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Cambiar fechas' }));
    expect(screen.getByRole('button', { name: 'Fecha de inicio: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: Elegir día' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.getByTestId('location')).toHaveTextContent('/equipos/1');
    expect(screen.getByTestId('location').textContent).not.toContain('start_date');
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.getPublicAvailability).toHaveBeenCalledTimes(1);
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('rejects a past start date before sending a customer reservation', async () => {
    vi.mocked(api.getPublicAvailability).mockResolvedValue({ equipment_id: 1, start_date: '2020-01-01', end_date: '2020-01-03', available: true, status: 'available' });
    renderProduct(session, '/equipos/1?start_date=2020-01-01&end_date=2020-01-03');
    expect(await screen.findByText('Elige hoy o una fecha posterior para reservar.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('offers administrators their own panel and does not expose customer confirmation', async () => {
    renderProduct({ ...session, role: 'admin', user: { ...session.user!, role: 'admin' } });
    expect(await screen.findByRole('link', { name: 'Ir al panel' })).toHaveAttribute('href', '/admin');
    expect(screen.queryByRole('button', { name: 'Confirmar reserva' })).not.toBeInTheDocument();
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('explains a global booking block and disables confirmation even if an older range read was available', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: false });
    renderProduct();
    expect(await screen.findByText('Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('rejects an unavailable full interval from the calendar even if an older range check was available', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValue({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true, unavailable_end_dates: ['2027-11-12'] });
    renderProduct();
    expect(await screen.findByText('No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('keeps confirmation blocked when the calendar fails and allows retrying its availability', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockRejectedValueOnce(new ApiError('Sin conexión.', 0));
    renderProduct();
    const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    await waitFor(() => expect(api.getPublicAvailability).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeDisabled();
    expect(screen.queryByText('Disponible del 10/11/2027 al 12/11/2027.')).not.toBeInTheDocument();
    expect(api.createMyReservation).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Reintentar calendario' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    expect(screen.getByText('Disponible del 10/11/2027 al 12/11/2027.')).toBeInTheDocument();
    expect(api.getPublicAvailabilityCalendar).toHaveBeenCalledTimes(2);
    expect(api.createMyReservation).not.toHaveBeenCalled();
  });

  it('distinguishes a temporary database wait from an unavailable range and keeps the selected dates', async () => {
    vi.mocked(api.createMyReservation).mockRejectedValueOnce(new ApiError('Base ocupada temporalmente.', 503));
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El sistema está ocupado temporalmente.');
    expect(screen.getByRole('button', { name: 'Fecha de inicio: 10/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fecha de devolución: 12/11/2027' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Volver a confirmar de forma segura' })).toBeEnabled();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('heading', { name: 'Reserva #42' })).not.toBeInTheDocument();
  });

  it('keeps a persisted confirmation and its focus if updating the calendar fails afterwards', async () => {
    vi.mocked(api.getPublicAvailabilityCalendar).mockResolvedValueOnce({ equipment_id: 1, start_date: '2027-11-01', end_date: '2027-12-01', occupied_ranges: [], can_book: true })
      .mockRejectedValueOnce(new ApiError('Sin conexión.', 0));
    renderProduct();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar reserva' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Confirmar reserva' }));
    expect(await screen.findByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo actualizar el calendario. Sin conexión.');
    expect(screen.getByRole('heading', { name: 'Reserva #42' })).toHaveFocus();
    expect(screen.getByText('Tu reserva se ha confirmado.')).toBeInTheDocument();
    expect(api.createMyReservation).toHaveBeenCalledTimes(1);
  });
});
