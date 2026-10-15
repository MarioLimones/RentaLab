import { beforeEach, expect, it, vi } from 'vitest';
import { api, limpiarTokenCsrf, suscribirSinAutorizacion } from './cliente';

const sesion = { authenticated: true, username: 'operador', expires_at: '2026-10-15T18:00:00Z', role: 'admin', user: null };
const cliente = { id: 7, name: 'Cliente de prueba', email: 'cliente@example.test', role: 'customer', active: true };
const peticionSimulada = vi.fn<typeof fetch>();

beforeEach(() => {
  limpiarTokenCsrf();
  peticionSimulada.mockReset();
  vi.stubGlobal('fetch', peticionSimulada);
});

it("consulta la sesión actual con credenciales del mismo origen y sin solicitar CSRF", async () => {
  peticionSimulada.mockResolvedValue(Response.json(sesion));
  await expect(api.sesion()).resolves.toEqual(sesion);
  expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/auth/session', expect.objectContaining({ credentials: 'same-origin' }));
});

it("registra un cliente mediante la sesión CSRF anónima sin iniciar sesión", async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json(cliente, { status: 201 }));
  const entrada = { name: cliente.name, email: cliente.email, password: 'ficticia de prueba' };
  await expect(api.registrar(entrada)).resolves.toEqual(cliente);
  expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual(['/api/auth/csrf', '/api/auth/register']);
  expect(peticionSimulada.mock.calls[1]?.[1]).toMatchObject({ method: 'POST', body: JSON.stringify(entrada), credentials: 'same-origin' });
  expect(new Headers(peticionSimulada.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('registration-token');
});

it("acepta una sesión de cliente con la identidad y el rol actuales del servidor", async () => {
  const sesionCliente = { ...sesion, username: cliente.email, role: 'customer', user: cliente };
  peticionSimulada.mockResolvedValue(Response.json(sesionCliente));
  await expect(api.sesion()).resolves.toEqual(sesionCliente);
});

it.each([
  { ...sesion, role: undefined },
  { ...sesion, role: 'owner' },
  { ...sesion, role: 'customer' },
  { ...sesion, role: 'admin', user: cliente },
  { ...sesion, role: 'customer', user: { ...cliente, active: false } },
])("rechaza roles del servidor ausentes o incoherentes sin asumir permisos de administración: %j", async (cuerpo) => {
  peticionSimulada.mockResolvedValue(Response.json(cuerpo));
  await expect(api.sesion()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it("rechaza una respuesta de registro que concede inesperadamente permisos de administración", async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json({ ...cliente, role: 'admin' }, { status: 201 }));
  await expect(api.registrar({ name: cliente.name, email: cliente.email, password: 'ficticia de prueba' }))
    .rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it("conserva el conflicto de registro para que el formulario lo explique", async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'registration-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'Ya existe una cuenta con ese correo.' }, { status: 409 }));
  await expect(api.registrar({ name: cliente.name, email: cliente.email, password: 'ficticia de prueba' }))
    .rejects.toMatchObject({ estado: 409, message: 'Ya existe una cuenta con ese correo.' });
});

it("obtiene CSRF para iniciar sesión y lo renueva al cerrar tras la rotación de sesión", async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'anonymous-token' }))
    .mockResolvedValueOnce(Response.json(sesion))
    .mockResolvedValueOnce(Response.json({ csrf_token: 'operator-token' }))
    .mockResolvedValueOnce(Response.json({ authenticated: false }));
  await expect(api.iniciarSesion({ username: 'operador', password: 'contraseña ficticia' })).resolves.toEqual(sesion);
  await expect(api.cerrarSesionUsuario()).resolves.toEqual({ authenticated: false });
  expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual(['/api/auth/csrf', '/api/auth/login', '/api/auth/csrf', '/api/auth/logout']);
  expect(new Headers(peticionSimulada.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('anonymous-token');
  expect(new Headers(peticionSimulada.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('operator-token');
  expect(peticionSimulada.mock.calls.every(([, opciones]) => opciones?.credentials === 'same-origin')).toBe(true);
});

it("comparte la solicitud CSRF inicial entre escrituras simultáneas", async () => {
  let resolverToken: ((respuesta: Response) => void) | undefined;
  peticionSimulada.mockImplementation((ruta) => ruta === '/api/auth/csrf'
    ? new Promise<Response>((resolver) => { resolverToken = resolver; })
    : Promise.resolve(Response.json({ detail: 'El equipo no existe.' }, { status: 404 })));
  const primero = api.cancelarReserva(1).catch((error: unknown) => error);
  const segundo = api.cancelarReserva(2).catch((error: unknown) => error);
  expect(peticionSimulada).toHaveBeenCalledTimes(1);
  resolverToken?.(Response.json({ csrf_token: 'shared-token' }));
  await Promise.all([primero, segundo]);
  expect(peticionSimulada).toHaveBeenCalledTimes(3);
  for (const [, opciones] of peticionSimulada.mock.calls.slice(1)) expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('shared-token');
});

it("avisa a la aplicación de un 401 operativo y descarta el token CSRF anterior", async () => {
  const oyente = vi.fn();
  const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
  try {
    peticionSimulada.mockResolvedValueOnce(Response.json({ detail: 'Sesión caducada.' }, { status: 401 }));
    await expect(api.listarEquipos()).rejects.toMatchObject({ estado: 401 });
    expect(oyente).toHaveBeenCalledTimes(1);
  } finally { cancelarSuscripcion(); }
});

it("evita convertir credenciales incorrectas en un aviso de sesión caducada de la aplicación", async () => {
  const oyente = vi.fn();
  const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
  try {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'token' }))
      .mockResolvedValueOnce(Response.json({ detail: 'Usuario o contraseña incorrectos.' }, { status: 401 }));
    await expect(api.iniciarSesion({ username: 'operador', password: 'incorrecta' })).rejects.toMatchObject({ estado: 401 });
    expect(oyente).not.toHaveBeenCalled();
  } finally { cancelarSuscripcion(); }
});

it("evita repetir una escritura rechazada por CSRF y obtiene un token nuevo en el siguiente intento", async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'old-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'Token CSRF no válido.' }, { status: 403 }))
    .mockResolvedValueOnce(Response.json({ csrf_token: 'new-token' }))
    .mockResolvedValueOnce(Response.json({ detail: 'El equipo no existe.' }, { status: 404 }));
  await expect(api.cancelarReserva(1)).rejects.toMatchObject({ estado: 403 });
  expect(peticionSimulada).toHaveBeenCalledTimes(2);
  await expect(api.cancelarReserva(1)).rejects.toMatchObject({ estado: 404 });
  expect(new Headers(peticionSimulada.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('new-token');
});

it.each([
  { authenticated: false },
  { ...sesion, username: 1 },
  { ...sesion, expires_at: '2026-10-15' },
])("comprueba la estructura de la respuesta de sesión: %j", async (cuerpo) => {
  peticionSimulada.mockResolvedValue(Response.json(cuerpo));
  await expect(api.sesion()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it("rechaza una respuesta CSRF no válida antes de enviar credenciales", async () => {
  peticionSimulada.mockResolvedValue(Response.json({ csrf_token: '' }));
  await expect(api.iniciarSesion({ username: 'operador', password: 'ficticia' })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  expect(peticionSimulada).toHaveBeenCalledTimes(1);
});

it("avisa de la pérdida de sesión aunque el cuerpo del 401 no sea JSON", async () => {
  const oyente = vi.fn();
  const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
  try {
    peticionSimulada.mockResolvedValue(new Response('Unauthorized', { status: 401 }));
    await expect(api.listarEquipos()).rejects.toMatchObject({ estado: 401 });
    expect(oyente).toHaveBeenCalledTimes(1);
  } finally { cancelarSuscripcion(); }
});

it("ignora un 401 tardío de una solicitud iniciada antes de un nuevo acceso correcto", async () => {
  let resolverSolicitudAnterior: ((respuesta: Response) => void) | undefined;
  const oyente = vi.fn();
  const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
  try {
    peticionSimulada.mockImplementation((ruta) => {
      if (ruta === '/api/equipment') return new Promise((resolver) => { resolverSolicitudAnterior = resolver; });
      return Promise.resolve(Response.json(ruta === '/api/auth/csrf' ? { csrf_token: 'new-token' } : sesion));
    });
    const anterior = api.listarEquipos().catch((error: unknown) => error);
    await api.iniciarSesion({ username: 'operador', password: 'ficticia' });
    resolverSolicitudAnterior?.(Response.json({ detail: 'Petición de sesión anterior.' }, { status: 401 }));
    await anterior;
    expect(oyente).not.toHaveBeenCalled();
  } finally { cancelarSuscripcion(); }
});

it("evita entregar resultados privados de una sesión anterior a un formulario antiguo", async () => {
  let resolverSolicitudAnterior: ((respuesta: Response) => void) | undefined;
  peticionSimulada.mockImplementation((ruta) => {
    if (ruta === '/api/equipment') return new Promise((resolver) => { resolverSolicitudAnterior = resolver; });
    return Promise.resolve(Response.json(ruta === '/api/auth/csrf' ? { csrf_token: 'new-token' } : sesion));
  });
  const anterior = api.listarEquipos();
  await api.iniciarSesion({ username: 'operador', password: 'ficticia' });
  resolverSolicitudAnterior?.(Response.json([{ id: 1, code: 'CAM-1', name: 'Cámara ficticia', category: 'Cámaras', description: '', active: true }]));
  await expect(anterior).rejects.toMatchObject({ estado: 401 });
});

it("avisa de un 401 operativo concurrente aunque otra solicitud reciba un 403 de CSRF", async () => {
  const pendiente = new Map<string, (respuesta: Response) => void>();
  const oyente = vi.fn();
  const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
  try {
    peticionSimulada.mockImplementation((ruta) => ruta === '/api/auth/csrf'
      ? Promise.resolve(Response.json({ csrf_token: 'old-token' }))
      : new Promise((resolver) => { pendiente.set(String(ruta), resolver); }));
    const primero = api.cancelarReserva(1).catch((error: unknown) => error);
    const segundo = api.cancelarReserva(2).catch((error: unknown) => error);
    await vi.waitFor(() => expect(pendiente.size).toBe(2));
    pendiente.get('/api/reservations/1/cancel')?.(Response.json({ detail: 'CSRF no válido.' }, { status: 403 }));
    await primero;
    pendiente.get('/api/reservations/2/cancel')?.(Response.json({ detail: 'Sesión caducada.' }, { status: 401 }));
    await segundo;
    expect(oyente).toHaveBeenCalledTimes(1);
  } finally { cancelarSuscripcion(); }
});
