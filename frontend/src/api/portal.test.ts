import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, limpiarTokenCsrf, suscribirSinAutorizacion } from './cliente';

const equipo = {
  id: 1,
  name: 'Cámara Aurora',
  category: 'Cámaras',
  public_description: 'Cámara para entrevistas.',
  technical_specs: { Resolución: '4K', Conexiones: 'USB-C' },
  image_url: null,
  image_fallback_url: '/api/public/images/equipment-placeholder.svg',
  active_reservations_count: 0,
};
const fechas = { start_date: '2026-11-10', end_date: '2026-11-12' };
const disponibilidad = { equipment_id: 1, ...fechas, available: true, status: 'available' };
const reserva = { id: 31, equipment_id: 1, ...fechas, status: 'confirmed' };
const incidencia = {
  id: 8, reservation_id: 31, title: 'Conector suelto', description: 'Se desconecta al moverlo.',
  status: 'open', public_response: '',
};
const sesion = {
  authenticated: true, username: 'cliente@example.test', expires_at: '2026-11-01T18:00:00Z', role: 'customer',
  user: { id: 7, name: 'Cliente', email: 'cliente@example.test', role: 'customer', active: true },
};
const peticionSimulada = vi.fn<typeof fetch>();

beforeEach(() => {
  limpiarTokenCsrf();
  peticionSimulada.mockReset();
  vi.stubGlobal('fetch', peticionSimulada);
});

describe("API del catálogo público", () => {
  it("consulta rutas públicas del mismo origen sin CSRF y codifica los filtros de búsqueda", async () => {
    const controlador = new AbortController();
    peticionSimulada.mockResolvedValueOnce(Response.json([equipo]));
    await expect(api.listarEquiposPublicos({ q: 'Cámara & lente', category: 'Vídeo/Foto' }, controlador.signal))
      .resolves.toEqual([equipo]);
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith(
      '/api/public/equipment?q=C%C3%A1mara+%26+lente&category=V%C3%ADdeo%2FFoto',
      expect.objectContaining({ signal: controlador.signal, credentials: 'same-origin' }),
    );
    expect(new Headers(peticionSimulada.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it("admite un catálogo vacío y el detalle público sin llamar a rutas de gestión", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json([])).mockResolvedValueOnce(Response.json(equipo));
    await expect(api.listarEquiposPublicos()).resolves.toEqual([]);
    await expect(api.obtenerEquipoPublico(1)).resolves.toEqual(equipo);
    expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual(['/api/public/equipment', '/api/public/equipment/1']);
  });

  it.each([0, 1, 4, Number.MAX_SAFE_INTEGER])("conserva un recuento válido de reservas activas en catálogo y detalle: %s", async (cantidad_reservas_activas) => {
    const producto = { ...equipo, active_reservations_count: cantidad_reservas_activas };
    peticionSimulada.mockResolvedValueOnce(Response.json([producto])).mockResolvedValueOnce(Response.json(producto));
    await expect(api.listarEquiposPublicos()).resolves.toEqual([producto]);
    await expect(api.obtenerEquipoPublico(1)).resolves.toEqual(producto);
  });

  it.each([undefined, null, -1, 1.5, '4', true, {}, [], Number.MAX_SAFE_INTEGER + 1])(
    "rechaza un recuento de reservas activas ausente o mal formado en catálogo y detalle: %j", async (cantidad_reservas_activas) => {
      const producto = { ...equipo, active_reservations_count: cantidad_reservas_activas };
      peticionSimulada.mockResolvedValueOnce(Response.json([producto])).mockResolvedValueOnce(Response.json(producto));
      await expect(api.listarEquiposPublicos()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
      await expect(api.obtenerEquipoPublico(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
    },
  );

  it.each([
    null,
    { ...equipo, code: 'PRIVATE-CODE' },
    { ...equipo, description: 'PRIVATE-NOTES' },
    { ...equipo, id: 0 },
    { ...equipo, technical_specs: ['4K'] },
    { ...equipo, technical_specs: { Resolución: 4000 } },
    { ...equipo, image_url: 'javascript:alert(1)' },
    { ...equipo, image_url: '//other.test/image.svg' },
    { ...equipo, image_url: 'https://user:secret@other.test/image.svg' },
    { ...equipo, image_url: '/api/public/images/../private.svg' },
    { ...equipo, image_url: 'https://other.test/image.svg?token=private' },
    { ...equipo, image_fallback_url: 'https://other.test/fallback.svg' },
  ])("rechaza respuestas del catálogo mal formadas o privadas: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerEquipoPublico(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each(['/api/public/images/cameras/aurora.svg', 'https://images.example.test/aurora.jpg', 'HTTPS://images.example.test/aurora.jpg'])(
    "acepta una imagen opcional segura y conserva la alternativa local: %s", async (url_imagen) => {
      peticionSimulada.mockResolvedValue(Response.json({ ...equipo, image_url: url_imagen }));
      await expect(api.obtenerEquipoPublico(1)).resolves.toMatchObject({ image_url: url_imagen, image_fallback_url: equipo.image_fallback_url });
      expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1', expect.any(Object));
    },
  );

  it("exige el estado de selección de fechas si faltan fechas y transmite días completos sin horas", async () => {
    const pendiente = { equipment_id: 1, start_date: null, end_date: null, available: null, status: 'select_dates' };
    peticionSimulada.mockResolvedValueOnce(Response.json(pendiente)).mockResolvedValueOnce(Response.json(disponibilidad));
    await expect(api.obtenerDisponibilidadPublica(1)).resolves.toEqual(pendiente);
    await expect(api.obtenerDisponibilidadPublica(1, fechas)).resolves.toEqual(disponibilidad);
    expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual([
      '/api/public/equipment/1/availability',
      '/api/public/equipment/1/availability?start_date=2026-11-10&end_date=2026-11-12',
    ]);
  });

  it.each([
    { ...disponibilidad, available: false },
    { ...disponibilidad, status: 'unavailable' },
    { ...disponibilidad, status: 'select_dates' },
    { ...disponibilidad, start_date: null },
    { ...disponibilidad, start_date: '2026-11-31' },
    { ...disponibilidad, start_date: '2027-02-29' },
    { ...disponibilidad, start_date: '2026-11-10T00:00:00' },
    { ...disponibilidad, end_date: '2026-11-10' },
    { ...disponibilidad, end_date: '2026-11-09' },
    { ...disponibilidad, reason: 'blocking_incident' },
    { ...disponibilidad, conflicting_reservation_ids: [31] },
  ])("rechaza una disponibilidad incoherente o motivos privados filtrados: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerDisponibilidadPublica(1, fechas)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("conserva un resultado no disponible sin exponer la causa interna", async () => {
    peticionSimulada.mockResolvedValue(Response.json({ ...disponibilidad, available: false, status: 'unavailable' }));
    await expect(api.obtenerDisponibilidadPublica(1, fechas)).resolves.toMatchObject({ available: false, status: 'unavailable' });
  });

  it("consulta el calendario público con fechas sin hora, intervalos limitados y sin datos privados ni CSRF", async () => {
    const controlador = new AbortController();
    const calendario = { equipment_id: 1, ...fechas, occupied_ranges: [fechas], can_book: true };
    peticionSimulada.mockResolvedValueOnce(Response.json(calendario));
    await expect(api.obtenerCalendarioDisponibilidadPublica(1, fechas, controlador.signal)).resolves.toEqual(calendario);
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/calendar?start_date=2026-11-10&end_date=2026-11-12', expect.objectContaining({ signal: controlador.signal, credentials: 'same-origin' }));
    expect(new Headers(peticionSimulada.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it("consulta devoluciones permitidas desde la recogida seleccionada sin exponer detalles de unidades físicas", async () => {
    const calendario = { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-11'] };
    peticionSimulada.mockResolvedValueOnce(Response.json(calendario));
    await expect(api.obtenerCalendarioDisponibilidadPublica(1, { ...fechas, booking_start: '2026-11-09' })).resolves.toEqual(calendario);
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/calendar?start_date=2026-11-10&end_date=2026-11-12&booking_start=2026-11-09', expect.any(Object));
  });

  it("consulta fechas públicas de reservas con la señal recibida, el mismo origen y sin CSRF", async () => {
    const controlador = new AbortController();
    const respuesta = { equipment_id: 1, reservations: [fechas] };
    peticionSimulada.mockResolvedValueOnce(Response.json(respuesta));
    await expect(api.obtenerFechasReservaPublica(1, controlador.signal)).resolves.toEqual(respuesta);
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/reservations', expect.objectContaining({ signal: controlador.signal, credentials: 'same-origin' }));
    expect(new Headers(peticionSimulada.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it("acepta una lista de reservas vacía y el identificador canónico de modelo de otra unidad", async () => {
    const respuesta = { equipment_id: 1, reservations: [] };
    peticionSimulada.mockResolvedValueOnce(Response.json(respuesta));
    await expect(api.obtenerFechasReservaPublica(9)).resolves.toEqual(respuesta);
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/9/reservations', expect.objectContaining({ signal: null }));
  });

  it("conserva intervalos originales de reservas duplicados y solapados sin recortarlos a la ventana del calendario", async () => {
    const respuesta = { equipment_id: 1, reservations: [
      { start_date: '2024-02-29', end_date: '2028-12-31' },
      fechas, fechas,
      { start_date: '2026-11-11', end_date: '2026-11-14' },
      { start_date: '2075-01-01', end_date: '2075-01-03' },
    ] };
    peticionSimulada.mockResolvedValueOnce(Response.json(respuesta));
    await expect(api.obtenerFechasReservaPublica(1)).resolves.toEqual(respuesta);
  });

  it.each([
    null,
    [],
    {},
    { equipment_id: 1 },
    { reservations: [] },
    { equipment_id: 0, reservations: [] },
    { equipment_id: 1.5, reservations: [] },
    { equipment_id: '1', reservations: [] },
    { equipment_id: 1, reservations: null },
    { equipment_id: 1, reservations: {} },
    { equipment_id: 1, reservations: [null] },
    { equipment_id: 1, reservations: [[]] },
    { equipment_id: 1, reservations: [{ start_date: fechas.start_date }] },
    { equipment_id: 1, reservations: [{ start_date: null, end_date: fechas.end_date }] },
    { equipment_id: 1, reservations: [{ start_date: '2026-11-31', end_date: '2026-12-02' }] },
    { equipment_id: 1, reservations: [{ start_date: '2027-02-29', end_date: '2027-03-02' }] },
    { equipment_id: 1, reservations: [{ start_date: '2026-11-10T00:00:00', end_date: fechas.end_date }] },
    { equipment_id: 1, reservations: [{ start_date: fechas.start_date, end_date: fechas.start_date }] },
    { equipment_id: 1, reservations: [{ start_date: fechas.end_date, end_date: fechas.start_date }] },
    { equipment_id: 1, reservations: [], customer_name: 'Private' },
    { equipment_id: 1, reservations: [{ ...fechas, id: 31 }] },
    { equipment_id: 1, reservations: [{ ...fechas, equipment_id: 7 }] },
    { equipment_id: 1, reservations: [{ ...fechas, customer_email: 'private@example.test' }] },
    { equipment_id: 1, reservations: [{ ...fechas, status: 'confirmed' }] },
  ])("rechaza fechas de reservas mal formadas o privadas: %j", async (respuesta) => {
    peticionSimulada.mockResolvedValueOnce(Response.json(respuesta));
    await expect(api.obtenerFechasReservaPublica(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("conserva la cancelación de una solicitud de fechas públicas de reservas", async () => {
    const controlador = new AbortController();
    controlador.abort();
    const fallo = new DOMException('Aborted', 'AbortError');
    peticionSimulada.mockRejectedValueOnce(fallo);
    await expect(api.obtenerFechasReservaPublica(1, controlador.signal)).rejects.toBe(fallo);
    expect(peticionSimulada.mock.calls[0]?.[1]?.signal).toBe(controlador.signal);
  });

  it("evita invalidar la cuenta o el token CSRF actual por un 401 de fechas públicas de reservas", async () => {
    const oyente = vi.fn();
    const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
    try {
      peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'current-token' }))
        .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }))
        .mockResolvedValueOnce(Response.json({ detail: 'Error público.' }, { status: 401 }))
        .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }));
      await api.cancelarMiReserva(31);
      await expect(api.obtenerFechasReservaPublica(1)).rejects.toMatchObject({ estado: 401 });
      await api.cancelarMiReserva(31);
      expect(oyente).not.toHaveBeenCalled();
      expect(peticionSimulada.mock.calls.filter(([ruta]) => ruta === '/api/auth/csrf')).toHaveLength(1);
    } finally { cancelarSuscripcion(); }
  });

  it.each([
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, customer_name: 'Private' },
    { equipment_id: 1, ...fechas, occupied_ranges: [{ ...fechas, reservation_id: 31 }], can_book: true },
    { equipment_id: 1, ...fechas, occupied_ranges: [{ ...fechas, customer_email: 'private@example.test' }], can_book: true },
    { equipment_id: 1, ...fechas, occupied_ranges: [{ start_date: '2026-11-09', end_date: '2026-11-12' }], can_book: true },
    { equipment_id: 1, ...fechas, occupied_ranges: [{ start_date: '2026-11-10', end_date: '2026-11-13' }], can_book: true },
    { equipment_id: 1, ...fechas, occupied_ranges: [{ start_date: '2026-11-10', end_date: '2026-11-10' }], can_book: true },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: 'true' },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, reason: 'Private incident' },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-09'] },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-12'] },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-31'] },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: [{ equipment_id: 2 }] },
    { equipment_id: 1, ...fechas, occupied_ranges: [], can_book: true, unavailable_end_dates: null },
  ])("rechaza datos de calendario privados o incoherentes: %j", async (calendario) => {
    peticionSimulada.mockResolvedValueOnce(Response.json(calendario));
    await expect(api.obtenerCalendarioDisponibilidadPublica(1, fechas)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("evita invalidar la sesión autenticada por un 401 público inesperado", async () => {
    const oyente = vi.fn();
    const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
    try {
      peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'current-token' }))
        .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }))
        .mockResolvedValueOnce(Response.json({ detail: 'Error público.' }, { status: 401 }))
        .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }));
      await api.cancelarMiReserva(31);
      await expect(api.listarEquiposPublicos()).rejects.toMatchObject({ estado: 401 });
      await api.cancelarMiReserva(31);
      expect(oyente).not.toHaveBeenCalled();
      expect(peticionSimulada.mock.calls.filter(([ruta]) => ruta === '/api/auth/csrf')).toHaveLength(1);
    } finally { cancelarSuscripcion(); }
  });

  it("mantiene utilizable una consulta del catálogo si la cuenta cambia durante su carga", async () => {
    let resolverCatalogo: ((respuesta: Response) => void) | undefined;
    peticionSimulada.mockImplementation((ruta) => {
      if (ruta === '/api/public/equipment') return new Promise((resolver) => { resolverCatalogo = resolver; });
      return Promise.resolve(Response.json(ruta === '/api/auth/csrf' ? { csrf_token: 'new-token' } : sesion));
    });
    const pendiente = api.listarEquiposPublicos();
    await api.iniciarSesion({ username: 'cliente@example.test', password: 'sólo prueba' });
    resolverCatalogo?.(Response.json([equipo]));
    await expect(pendiente).resolves.toEqual([equipo]);
  });
});

describe("API de cliente", () => {
  it("envía una clave opcional estable de idempotencia separada de los campos permitidos de reserva", async () => {
    const key = 'a26af448-f231-4ac7-9d8b-9794d2ae7541';
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(reserva, { status: 201 }))
      .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }, { status: 201 }));
    await expect(api.crearMiReserva({ equipment_id: 1, ...fechas }, key)).resolves.toEqual(reserva);
    await expect(api.crearMiReserva({ equipment_id: 1, ...fechas }, key)).resolves.toMatchObject({ id: 31, status: 'cancelled' });
    for (const [, opciones] of peticionSimulada.mock.calls.slice(1)) {
      expect(new Headers(opciones?.headers).get('Idempotency-Key')).toBe(key);
      expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('customer-token');
      expect(JSON.parse(opciones?.body as string)).toEqual({ equipment_id: 1, ...fechas });
    }
  });
  it("lista y consulta solo la proyección /me y mantiene las respuestas sin campos de identidad", async () => {
    const controlador = new AbortController();
    peticionSimulada.mockResolvedValueOnce(Response.json([reserva])).mockResolvedValueOnce(Response.json(reserva))
      .mockResolvedValueOnce(Response.json([incidencia])).mockResolvedValueOnce(Response.json(incidencia));
    await expect(api.listarMisReservas(controlador.signal)).resolves.toEqual([reserva]);
    await expect(api.obtenerMiReserva(31, controlador.signal)).resolves.toEqual(reserva);
    await expect(api.listarMisIncidencias(controlador.signal)).resolves.toEqual([incidencia]);
    await expect(api.obtenerMiIncidencia(8, controlador.signal)).resolves.toEqual(incidencia);
    expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual([
      '/api/me/reservations', '/api/me/reservations/31', '/api/me/incidents', '/api/me/incidents/8',
    ]);
    expect(peticionSimulada.mock.calls.every(([, opciones]) => opciones?.credentials === 'same-origin' && opciones.signal === controlador.signal)).toBe(true);
  });

  it("crea una reserva solo con los campos permitidos de equipo y fechas utilizando CSRF", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(reserva, { status: 201 }));
    const entrada = { equipment_id: 1, ...fechas, customer_id: 99, status: 'cancelled', customer_email: 'other@example.test' };
    await expect(api.crearMiReserva(entrada)).resolves.toEqual(reserva);
    expect(peticionSimulada.mock.calls.map(([ruta]) => ruta)).toEqual(['/api/auth/csrf', '/api/me/reservations']);
    const opciones = peticionSimulada.mock.calls[1]?.[1];
    expect(opciones).toMatchObject({ method: 'POST', body: JSON.stringify({ equipment_id: 1, ...fechas }), credentials: 'same-origin' });
    expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('customer-token');
  });

  it("cancela sin enviar campos y conserva el historial de cancelación devuelto", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }));
    await expect(api.cancelarMiReserva(31)).resolves.toMatchObject({ ...fechas, status: 'cancelled' });
    expect(peticionSimulada.mock.calls[1]).toEqual(['/api/me/reservations/31/cancel', expect.objectContaining({ method: 'POST' })]);
    expect(peticionSimulada.mock.calls[1]?.[1]?.body).toBeUndefined();
  });

  it("comunica una incidencia por reserva únicamente con el título y la descripción del cliente", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(incidencia, { status: 201 }));
    const entrada = { title: incidencia.title, description: incidencia.description, blocking: true };
    await expect(api.crearMiIncidencia(31, entrada)).resolves.toEqual(incidencia);
    expect(peticionSimulada.mock.calls[1]).toEqual(['/api/me/reservations/31/incidents', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ title: incidencia.title, description: incidencia.description }),
    })]);
  });

  it.each([
    { ...reserva, customer_name: 'Private identity' },
    { ...reserva, customer_user_id: 99 },
    { ...reserva, status: 'pending' },
    { ...reserva, start_date: '2026-02-30' },
    { ...reserva, end_date: reserva.start_date },
  ])("rechaza esquemas privados de reserva incompatibles o más amplios: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerMiReserva(31)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each([
    { ...incidencia, internal_notes: 'Private management note' },
    { ...incidencia, resolution: 'Internal resolution' },
    { ...incidencia, blocking: true },
    { ...incidencia, reservation_id: null },
    { ...incidencia, public_response: null },
  ])("rechaza esquemas privados de incidencia incompatibles o más amplios: %j", async (cuerpo) => {
    peticionSimulada.mockResolvedValue(Response.json(cuerpo));
    await expect(api.obtenerMiIncidencia(8)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("conserva un conflicto de reserva sin reintentar ni crear otra reserva", async () => {
    const mensaje = 'La disponibilidad ha cambiado. Consulta otra vez y elige otro intervalo.';
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ detail: mensaje }, { status: 409 }));
    await expect(api.crearMiReserva({ equipment_id: 1, ...fechas })).rejects.toMatchObject({ estado: 409, message: mensaje });
    expect(peticionSimulada.mock.calls.filter(([ruta]) => ruta === '/api/me/reservations')).toHaveLength(1);
  });

  it("devuelve errores de validación de campos para el formulario de incidencias", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ detail: [{ loc: ['body', 'title'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.crearMiIncidencia(31, { title: '', description: incidencia.description }))
      .rejects.toMatchObject({ estado: 422, campos: { title: 'Este campo es obligatorio.' } });
  });

  it("invalida la sesión ante un 401 privado y conserva errores 403 y 404", async () => {
    const oyente = vi.fn();
    const cancelarSuscripcion = suscribirSinAutorizacion(oyente);
    try {
      for (const estado of [404, 403, 401]) {
        peticionSimulada.mockResolvedValueOnce(Response.json({ detail: 'Recurso no disponible.' }, { status: estado }));
        await expect(api.obtenerMiReserva(31)).rejects.toMatchObject({ estado });
      }
      expect(oyente).toHaveBeenCalledTimes(1);
    } finally { cancelarSuscripcion(); }
  });

  it("impide presentar la lista pendiente de reservas de una cuenta anterior después de un nuevo acceso", async () => {
    let resolverCuentaAnterior: ((respuesta: Response) => void) | undefined;
    peticionSimulada.mockImplementation((ruta) => {
      if (ruta === '/api/me/reservations') return new Promise((resolver) => { resolverCuentaAnterior = resolver; });
      return Promise.resolve(Response.json(ruta === '/api/auth/csrf' ? { csrf_token: 'new-token' } : sesion));
    });
    const pendiente = api.listarMisReservas();
    await api.iniciarSesion({ username: 'cliente@example.test', password: 'sólo prueba' });
    resolverCuentaAnterior?.(Response.json([reserva]));
    await expect(pendiente).rejects.toMatchObject({ estado: 401 });
  });

  it("obtiene CSRF nuevo después de una escritura rechazada sin repetirla automáticamente", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'old-token' }))
      .mockResolvedValueOnce(Response.json({ detail: 'CSRF no válido.' }, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ csrf_token: 'new-token' }))
      .mockResolvedValueOnce(Response.json({ ...reserva, status: 'cancelled' }));
    await expect(api.cancelarMiReserva(31)).rejects.toMatchObject({ estado: 403 });
    expect(peticionSimulada).toHaveBeenCalledTimes(2);
    await api.cancelarMiReserva(31);
    expect(new Headers(peticionSimulada.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('new-token');
  });
});
