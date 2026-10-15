import { beforeEach, expect, it, vi } from 'vitest';
import { api, clearCsrfToken, subscribeToUnauthorized } from './client';

const session = { authenticated: true, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin', user: null };
const customer = { id: 7, name: 'Cliente de prueba', email: 'cliente@example.test', role: 'customer', active: true };
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  clearCsrfToken();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

it('reads the current session with same-origin credentials and no CSRF request', async () => {
  fetchMock.mockResolvedValue(Response.json(session));
  await expect(api.session()).resolves.toEqual(session);
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/auth/session', expect.objectContaining({ credentials: 'same-origin' }));
});

it('registers a customer through the anonymous CSRF session without logging them in', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json(customer, { status: 201 }));
  const input = { name: customer.name, email: customer.email, password: 'ficticia de prueba' };
  await expect(api.register(input)).resolves.toEqual(customer);
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/auth/csrf', '/api/auth/register']);
  expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'POST', body: JSON.stringify(input), credentials: 'same-origin' });
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('registration-token');
});

it('accepts a customer session with the current server identity and role', async () => {
  const customerSession = { ...session, username: customer.email, role: 'customer', user: customer };
  fetchMock.mockResolvedValue(Response.json(customerSession));
  await expect(api.session()).resolves.toEqual(customerSession);
});

it.each([
  { ...session, role: undefined },
  { ...session, role: 'owner' },
  { ...session, role: 'customer' },
  { ...session, role: 'admin', user: customer },
  { ...session, role: 'customer', user: { ...customer, active: false } },
])('rejects missing or inconsistent server roles rather than assuming admin: %j', async (body) => {
  fetchMock.mockResolvedValue(Response.json(body));
  await expect(api.session()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('rejects a registration response that unexpectedly grants administrator permissions', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json({ ...customer, role: 'admin' }, { status: 201 }));
  await expect(api.register({ name: customer.name, email: customer.email, password: 'ficticia de prueba' }))
    .rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('preserves a registration conflict for the form to explain it', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'Ya existe una cuenta con ese correo.' }, { status: 409 }));
  await expect(api.register({ name: customer.name, email: customer.email, password: 'ficticia de prueba' }))
    .rejects.toMatchObject({ status: 409, message: 'Ya existe una cuenta con ese correo.' });
});

it('obtains CSRF for login and refreshes it after session rotation for logout', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'anonymous-token' }))
    .mockResolvedValueOnce(Response.json(session))
    .mockResolvedValueOnce(Response.json({ csrf_token: 'operator-token' }))
    .mockResolvedValueOnce(Response.json({ authenticated: false }));
  await expect(api.login({ username: 'operador', password: 'contraseña ficticia' })).resolves.toEqual(session);
  await expect(api.logout()).resolves.toEqual({ authenticated: false });
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/auth/csrf', '/api/auth/login', '/api/auth/csrf', '/api/auth/logout']);
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('anonymous-token');
  expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('operator-token');
  expect(fetchMock.mock.calls.every(([, options]) => options?.credentials === 'same-origin')).toBe(true);
});

it('shares the initial CSRF request between simultaneous writes', async () => {
  let resolveToken: ((response: Response) => void) | undefined;
  fetchMock.mockImplementation((path) => path === '/api/auth/csrf'
    ? new Promise<Response>((resolve) => { resolveToken = resolve; })
    : Promise.resolve(Response.json({ detail: 'El equipo no existe.' }, { status: 404 })));
  const first = api.cancelReservation(1).catch((error: unknown) => error);
  const second = api.cancelReservation(2).catch((error: unknown) => error);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  resolveToken?.(Response.json({ csrf_token: 'shared-token' }));
  await Promise.all([first, second]);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  for (const [, options] of fetchMock.mock.calls.slice(1)) expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('shared-token');
});

it('notifies the application on a business 401 and discards the old CSRF token', async () => {
  const listener = vi.fn();
  const unsubscribe = subscribeToUnauthorized(listener);
  try {
    fetchMock.mockResolvedValueOnce(Response.json({ detail: 'Sesión caducada.' }, { status: 401 }));
    await expect(api.listEquipment()).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
  } finally { unsubscribe(); }
});

it('does not turn invalid login credentials into an application session-expired event', async () => {
  const listener = vi.fn();
  const unsubscribe = subscribeToUnauthorized(listener);
  try {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'token' }))
      .mockResolvedValueOnce(Response.json({ detail: 'Usuario o contraseña incorrectos.' }, { status: 401 }));
    await expect(api.login({ username: 'operador', password: 'incorrecta' })).rejects.toMatchObject({ status: 401 });
    expect(listener).not.toHaveBeenCalled();
  } finally { unsubscribe(); }
});

it('does not replay a write rejected by CSRF and obtains a new token on the next attempt', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'old-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'Token CSRF no válido.' }, { status: 403 }))
    .mockResolvedValueOnce(Response.json({ csrf_token: 'new-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'El equipo no existe.' }, { status: 404 }));
  await expect(api.cancelReservation(1)).rejects.toMatchObject({ status: 403 });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  await expect(api.cancelReservation(1)).rejects.toMatchObject({ status: 404 });
  expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('new-token');
});

it.each([
  { authenticated: false },
  { ...session, username: 1 },
  { ...session, expires_at: '2026-10-15' },
])('checks the session response structure: %j', async (body) => {
  fetchMock.mockResolvedValue(Response.json(body));
  await expect(api.session()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('rejects an invalid CSRF response before sending credentials', async () => {
  fetchMock.mockResolvedValue(Response.json({ csrf_token: '' }));
  await expect(api.login({ username: 'operador', password: 'ficticia' })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('notifies session loss even when the 401 body is not JSON', async () => {
  const listener = vi.fn();
  const unsubscribe = subscribeToUnauthorized(listener);
  try {
    fetchMock.mockResolvedValue(new Response('Unauthorized', { status: 401 }));
    await expect(api.listEquipment()).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
  } finally { unsubscribe(); }
});

it('ignores a delayed 401 from a request started before a successful new login', async () => {
  let resolveOldRequest: ((response: Response) => void) | undefined;
  const listener = vi.fn();
  const unsubscribe = subscribeToUnauthorized(listener);
  try {
    fetchMock.mockImplementation((path) => {
      if (path === '/api/equipment') return new Promise((resolve) => { resolveOldRequest = resolve; });
      return Promise.resolve(Response.json(path === '/api/auth/csrf' ? { csrf_token: 'new-token' } : session));
    });
    const previous = api.listEquipment().catch((error: unknown) => error);
    await api.login({ username: 'operador', password: 'ficticia' });
    resolveOldRequest?.(Response.json({ detail: 'Petición de sesión anterior.' }, { status: 401 }));
    await previous;
    expect(listener).not.toHaveBeenCalled();
  } finally { unsubscribe(); }
});

it('does not deliver private results from a previous session to an old form', async () => {
  let resolveOldRequest: ((response: Response) => void) | undefined;
  fetchMock.mockImplementation((path) => {
    if (path === '/api/equipment') return new Promise((resolve) => { resolveOldRequest = resolve; });
    return Promise.resolve(Response.json(path === '/api/auth/csrf' ? { csrf_token: 'new-token' } : session));
  });
  const previous = api.listEquipment();
  await api.login({ username: 'operador', password: 'ficticia' });
  resolveOldRequest?.(Response.json([{ id: 1, code: 'CAM-1', name: 'Cámara ficticia', category: 'Cámaras', description: '', active: true }]));
  await expect(previous).rejects.toMatchObject({ status: 401 });
});

it('still notifies a concurrent business 401 after another request receives a CSRF 403', async () => {
  const pending = new Map<string, (response: Response) => void>();
  const listener = vi.fn();
  const unsubscribe = subscribeToUnauthorized(listener);
  try {
    fetchMock.mockImplementation((path) => path === '/api/auth/csrf'
      ? Promise.resolve(Response.json({ csrf_token: 'old-token' }))
      : new Promise((resolve) => { pending.set(String(path), resolve); }));
    const first = api.cancelReservation(1).catch((error: unknown) => error);
    const second = api.cancelReservation(2).catch((error: unknown) => error);
    await vi.waitFor(() => expect(pending.size).toBe(2));
    pending.get('/api/reservations/1/cancel')?.(Response.json({ detail: 'CSRF no válido.' }, { status: 403 }));
    await first;
    pending.get('/api/reservations/2/cancel')?.(Response.json({ detail: 'Sesión caducada.' }, { status: 401 }));
    await second;
    expect(listener).toHaveBeenCalledTimes(1);
  } finally { unsubscribe(); }
});
