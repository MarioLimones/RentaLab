import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import { api, ApiError } from './api/client';

const session = { authenticated: true as const, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin' as const, user: null };
const customer = { id: 7, name: 'Cliente de prueba', email: 'cliente@example.test', role: 'customer' as const, active: true };
const customerSession = { ...session, username: customer.email, role: 'customer' as const, user: customer };
const dates = { start_date: '2099-11-10', end_date: '2099-11-12' };
const equipment = {
  id: 1, name: 'Cámara Aurora', category: 'Cámaras', public_description: 'Cámara ficticia para entrevistas.',
  technical_specs: { Resolución: '4K' }, image_url: null, image_fallback_url: '/api/public/images/equipment-placeholder.svg', active_reservations_count: 0,
};
const productDestination = `/equipos/1?start_date=${dates.start_date}&end_date=${dates.end_date}`;

function Location() { const location = useLocation(); return <span data-testid="location">{location.pathname}{location.search}</span>; }
function renderApp(path = '/admin/importaciones') { return render(<MemoryRouter initialEntries={[path]}><App /><Location /></MemoryRouter>); }
function fillLogin() {
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: 'operador' } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
}

beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok' });
  vi.spyOn(api, 'session').mockRejectedValue(new ApiError('Se requiere iniciar sesión.', 401));
  vi.spyOn(api, 'listEquipment').mockResolvedValue([]);
  vi.spyOn(api, 'listPublicEquipment').mockResolvedValue([]);
  vi.spyOn(api, 'listReservations').mockResolvedValue([]);
  vi.spyOn(api, 'listIncidents').mockResolvedValue([]);
});

it('does not render private pages or load their data while checking the session', async () => {
  let resolveSession: ((value: typeof session) => void) | undefined;
  vi.mocked(api.session).mockImplementation(() => new Promise((resolve) => { resolveSession = resolve; }));
  renderApp('/admin/equipos');
  expect(screen.getByRole('status')).toHaveTextContent('Comprobando la sesión');
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listEquipment).not.toHaveBeenCalled();
  await waitFor(() => expect(api.session).toHaveBeenCalledTimes(1));
  await act(async () => { resolveSession?.(session); });
  expect(await screen.findByRole('heading', { name: 'Equipos', level: 1 })).toBeInTheDocument();
});

it('signs in through the server and keeps the requested deep route', async () => {
  vi.spyOn(api, 'login').mockResolvedValue(session);
  renderApp();
  await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 });
  fillLogin();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  expect(api.login).toHaveBeenCalledWith({ username: 'operador', password: 'contraseña ficticia' });
  expect(screen.getByTestId('location')).toHaveTextContent('/admin/importaciones');
  expect(screen.queryByLabelText('Contraseña')).not.toBeInTheDocument();
  expect(screen.getByText('operador')).toBeInTheDocument();
});

it('keeps entered values after invalid credentials and focuses the accessible error', async () => {
  vi.spyOn(api, 'login').mockRejectedValue(new ApiError('Usuario o contraseña incorrectos.', 401));
  renderApp();
  await screen.findByLabelText('Usuario');
  fillLogin();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Usuario o contraseña incorrectos.');
  await waitFor(() => expect(alert).toHaveFocus());
  expect(screen.getByLabelText('Usuario')).toHaveValue('operador');
  expect(screen.getByLabelText('Contraseña')).toHaveValue('contraseña ficticia');
});

it('provides labels, autocomplete, keyboard submission and a password visibility control', async () => {
  vi.spyOn(api, 'login').mockResolvedValue(session);
  const user = userEvent.setup();
  renderApp();
  const username = await screen.findByLabelText('Usuario');
  const password = screen.getByLabelText('Contraseña');
  expect(username).toHaveAttribute('autocomplete', 'username');
  expect(password).toHaveAttribute('autocomplete', 'current-password');
  expect(password).toHaveAttribute('type', 'password');
  await user.click(screen.getByRole('button', { name: 'Mostrar contraseña' }));
  expect(password).toHaveAttribute('type', 'text');
  expect(screen.getByRole('button', { name: 'Ocultar contraseña' })).toHaveAttribute('aria-pressed', 'true');
  await user.type(username, 'operador');
  await user.type(password, 'ficticia{Enter}');
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
});

it('shows field errors without submitting empty credentials', async () => {
  const login = vi.spyOn(api, 'login');
  renderApp();
  await screen.findByLabelText('Usuario');
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
  expect(screen.getByLabelText('Usuario')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('aria-invalid', 'true');
  expect(login).not.toHaveBeenCalled();
});

it('waits for successful logout before removing private data and preserves the deep route', async () => {
  vi.mocked(api.session).mockResolvedValue(session);
  vi.spyOn(api, 'logout').mockResolvedValue({ authenticated: false });
  renderApp();
  await screen.findByRole('heading', { name: 'Importaciones', level: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
  expect(api.logout).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/acceso?next=%2Fadmin%2Fimportaciones');
});

it('keeps the authenticated screen when the server could not close the session', async () => {
  vi.mocked(api.session).mockResolvedValue(session);
  vi.spyOn(api, 'logout').mockRejectedValue(new ApiError('No se pudo conectar con el servidor.', 0));
  renderApp();
  await screen.findByRole('heading', { name: 'Importaciones', level: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar');
  expect(screen.getByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeEnabled();
});

it('handles a real business 401 by unmounting private screens and showing login', async () => {
  vi.mocked(api.session).mockResolvedValue(session);
  vi.mocked(api.listEquipment).mockRestore();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'Sesión caducada.' }, { status: 401 })));
  renderApp('/admin/equipos');
  await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 });
  expect(screen.queryByRole('heading', { name: 'Equipos', level: 1 })).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(screen.getByText('La sesión ha caducado. Inicia sesión para continuar.')).toBeInTheDocument();
});

it('offers an explicit retry when the session cannot be checked', async () => {
  vi.mocked(api.session).mockRejectedValueOnce(new ApiError('No se pudo conectar.', 0)).mockResolvedValueOnce(session);
  renderApp();
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar.');
  expect(screen.queryByLabelText('Contraseña')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Volver a comprobar' }));
  expect(await screen.findByRole('heading', { name: 'Importaciones', level: 1 })).toBeInTheDocument();
  await waitFor(() => expect(api.session).toHaveBeenCalledTimes(2));
});

it('registers a customer, confirms success and returns to login with their email', async () => {
  vi.spyOn(api, 'register').mockResolvedValue(customer);
  const login = vi.spyOn(api, 'login');
  renderApp();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  expect(screen.getByRole('heading', { name: 'Crear cuenta', level: 1 })).toBeInTheDocument();
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('type', 'email');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('autocomplete', 'new-password');
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: customer.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  expect(screen.queryByLabelText(/rol/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
  expect(screen.getByText('Cuenta creada. Ya puedes iniciar sesión.')).toHaveAttribute('role', 'status');
  expect(screen.getByLabelText('Usuario')).toHaveValue(customer.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('');
  expect(api.register).toHaveBeenCalledWith({ name: customer.name, email: customer.email, password: 'contraseña ficticia' });
  expect(login).not.toHaveBeenCalled();
});

it('preserves registration values after a duplicate email and focuses the error', async () => {
  vi.spyOn(api, 'register').mockRejectedValue(new ApiError('Ya existe una cuenta con ese correo.', 409));
  renderApp();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: customer.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Ya existe una cuenta con ese correo.');
  await waitFor(() => expect(alert).toHaveFocus());
  expect(screen.getByLabelText('Nombre')).toHaveValue(customer.name);
  expect(screen.getByLabelText('Correo electrónico')).toHaveValue(customer.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('contraseña ficticia');
});

it('explains registration field errors without sending an incomplete form', async () => {
  const register = vi.spyOn(api, 'register');
  renderApp();
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Revisa los campos indicados.');
  expect(screen.getByLabelText('Nombre')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('Contraseña')).toHaveAttribute('aria-invalid', 'true');
  expect(register).not.toHaveBeenCalled();
});

it('denies administrative deep links to a customer without loading private management data', async () => {
  vi.mocked(api.session).mockResolvedValue({ ...session, username: customer.email, role: 'customer', user: customer });
  const reservations = vi.mocked(api.listReservations);
  const incidents = vi.mocked(api.listIncidents);
  renderApp('/admin/reservas');
  expect(await screen.findByRole('heading', { name: 'Acceso restringido', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Volver a mi zona' })).toHaveAttribute('href', '/mi-cuenta');
  expect(api.listEquipment).not.toHaveBeenCalled();
  expect(reservations).not.toHaveBeenCalled();
  expect(incidents).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('link', { name: 'Volver a mi zona' }));
  expect(await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 })).toBeInTheDocument();
  expect(screen.getByText(customer.name)).toBeInTheDocument();
  expect(screen.getByText(customer.email)).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/mi-cuenta');
  expect(screen.queryByRole('link', { name: 'Panel de administración' })).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: 'Principal' })).not.toBeInTheDocument();
  expect(api.listEquipment).not.toHaveBeenCalled();
  expect(reservations).not.toHaveBeenCalled();
  expect(incidents).not.toHaveBeenCalled();
});

it('lets a customer sign in with their email and close the session', async () => {
  vi.spyOn(api, 'login').mockResolvedValue({ ...session, username: customer.email, role: 'customer', user: customer });
  vi.spyOn(api, 'logout').mockResolvedValue({ authenticated: false });
  renderApp('/acceso');
  fireEvent.change(await screen.findByLabelText('Usuario'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 });
  expect(api.login).toHaveBeenCalledWith({ username: customer.email, password: 'contraseña ficticia' });
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Acceder a RentaLab', level: 1 })).toBeInTheDocument();
});

it.each(['https://other.example.test/collect', '//other.example.test/collect', '/admin/importaciones'])(
  'ignores an external or administrative login destination for a customer: %s', async (next) => {
    vi.spyOn(api, 'login').mockResolvedValue(customerSession);
    renderApp(`/acceso?next=${encodeURIComponent(next)}`);
    await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
    fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: customer.email } });
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
    await screen.findByRole('heading', { name: 'Mi cuenta', level: 1 });
    expect(screen.getByTestId('location')).toHaveTextContent('/mi-cuenta');
    expect(api.listEquipment).not.toHaveBeenCalled();
  },
);

it('sends administrators to /admin when the login destination is a client product', async () => {
  vi.spyOn(api, 'login').mockResolvedValue(session);
  renderApp(`/acceso?next=${encodeURIComponent(productDestination)}`);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  fillLogin();
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: 'Resumen', level: 1 })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent('/admin');
});

it('keeps the equipment dates through registration without logging in or reserving automatically', async () => {
  vi.spyOn(api, 'register').mockResolvedValue(customer);
  const login = vi.spyOn(api, 'login');
  const create = vi.spyOn(api, 'createMyReservation');
  renderApp(`/acceso?next=${encodeURIComponent(productDestination)}`);
  fireEvent.click(await within(await screen.findByRole('main')).findByRole('link', { name: 'Crear cuenta' }));
  expect(screen.getByTestId('location')).toHaveTextContent(`/registro?next=${encodeURIComponent(productDestination)}`);
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: customer.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(productDestination)}`);
  expect(screen.getByLabelText('Usuario')).toHaveValue(customer.email);
  expect(screen.getByLabelText('Contraseña')).toHaveValue('');
  expect(login).not.toHaveBeenCalled();
  expect(create).not.toHaveBeenCalled();
});

it('uses backend validation errors beside the corresponding registration fields', async () => {
  vi.spyOn(api, 'register').mockRejectedValue(new ApiError('Revisa el correo.', 422, { email: 'Introduce otro correo válido.' }));
  renderApp('/registro');
  await screen.findByRole('heading', { name: 'Crear cuenta' });
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: customer.name } });
  fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear mi cuenta' }));
  expect(await screen.findByText('Introduce otro correo válido.')).toBeInTheDocument();
  expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true');
});

it('retains equipment and date-only values across login and requires a separate confirmation', async () => {
  vi.spyOn(api, 'getPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'getPublicAvailabilityCalendar').mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'getPublicAvailability').mockResolvedValue({ equipment_id: 1, ...dates, available: true, status: 'available' });
  vi.spyOn(api, 'login').mockResolvedValue(customerSession);
  const create = vi.spyOn(api, 'createMyReservation').mockResolvedValue({ id: 31, equipment_id: 1, ...dates, status: 'confirmed' });
  renderApp(productDestination);
  const reserve = await screen.findByRole('button', { name: 'Acceder para reservar' });
  await waitFor(() => expect(reserve).toBeEnabled());
  fireEvent.click(reserve);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(productDestination)}`);
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: customer.email } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contraseña ficticia' } });
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));
  expect(await screen.findByRole('heading', { name: equipment.name, level: 1 })).toBeInTheDocument();
  expect(screen.getByTestId('location')).toHaveTextContent(productDestination);
  const displayDate = (value: string) => value.split('-').reverse().join('/');
  expect(screen.getByRole('button', { name: `Fecha de inicio: ${displayDate(dates.start_date)}` })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: `Fecha de devolución: ${displayDate(dates.end_date)}` })).toBeInTheDocument();
  expect(create).not.toHaveBeenCalled();
  const confirm = screen.getByRole('button', { name: 'Confirmar reserva' });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  expect(await screen.findByRole('link', { name: 'Ver mi reserva' })).toHaveAttribute('href', '/mis-reservas/31');
  expect(create).toHaveBeenCalledExactlyOnceWith({ equipment_id: 1, ...dates }, expect.any(String));
});

it('preserves equipment dates when switching access and registration through the header', async () => {
  vi.spyOn(api, 'getPublicEquipment').mockResolvedValue(equipment);
  vi.spyOn(api, 'getPublicAvailabilityCalendar').mockImplementation(async (equipment_id, range) => ({ equipment_id, ...range, occupied_ranges: [], can_book: true }));
  vi.spyOn(api, 'getPublicAvailability').mockResolvedValue({ equipment_id: 1, ...dates, available: true, status: 'available' });
  const create = vi.spyOn(api, 'createMyReservation');
  renderApp(productDestination);
  const access = await screen.findByRole('link', { name: 'Acceder' });
  expect(access).toHaveAttribute('href', `/acceso?next=${encodeURIComponent(productDestination)}`);
  fireEvent.click(access);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  const registration = within(screen.getByRole('banner')).getByRole('link', { name: 'Crear cuenta' });
  expect(registration).toHaveAttribute('href', `/registro?next=${encodeURIComponent(productDestination)}`);
  fireEvent.click(registration);
  await screen.findByRole('heading', { name: 'Crear cuenta' });
  const returnToAccess = screen.getByRole('link', { name: 'Acceder' });
  expect(returnToAccess).toHaveAttribute('href', `/acceso?next=${encodeURIComponent(productDestination)}`);
  fireEvent.click(returnToAccess);
  await screen.findByRole('heading', { name: 'Acceder a RentaLab' });
  expect(screen.getByTestId('location')).toHaveTextContent(`/acceso?next=${encodeURIComponent(productDestination)}`);
  expect(create).not.toHaveBeenCalled();
});
