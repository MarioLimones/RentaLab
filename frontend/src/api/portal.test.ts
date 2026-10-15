import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, clearCsrfToken, subscribeToUnauthorized } from './client';

const equipment = {
  id: 1,
  name: 'Cámara Aurora',
  category: 'Cámaras',
  public_description: 'Cámara para entrevistas.',
  technical_specs: { Resolución: '4K', Conexiones: 'USB-C' },
  image_url: null,
  image_fallback_url: '/api/public/images/equipment-placeholder.svg',
  active_reservations_count: 0,
};
const dates = { start_date: '2026-11-10', end_date: '2026-11-12' };
const availability = { equipment_id: 1, ...dates, available: true, status: 'available' };
const reservation = { id: 31, equipment_id: 1, ...dates, status: 'confirmed' };
const incident = {
  id: 8, reservation_id: 31, title: 'Conector suelto', description: 'Se desconecta al moverlo.',
  status: 'open', public_response: '',
};
const session = {
  authenticated: true, username: 'cliente@example.test', expires_at: '2026-11-01T18:00:00Z', role: 'customer',
  user: { id: 7, name: 'Cliente', email: 'cliente@example.test', role: 'customer', active: true },
};
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  clearCsrfToken();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

describe('public catalogue API', () => {
  it('queries public routes on the same origin without CSRF and encodes search filters', async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValueOnce(Response.json([equipment]));
    await expect(api.listPublicEquipment({ q: 'Cámara & lente', category: 'Vídeo/Foto' }, controller.signal))
      .resolves.toEqual([equipment]);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/public/equipment?q=C%C3%A1mara+%26+lente&category=V%C3%ADdeo%2FFoto',
      expect.objectContaining({ signal: controller.signal, credentials: 'same-origin' }),
    );
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('supports an empty catalogue and the public detail without calling management endpoints', async () => {
    fetchMock.mockResolvedValueOnce(Response.json([])).mockResolvedValueOnce(Response.json(equipment));
    await expect(api.listPublicEquipment()).resolves.toEqual([]);
    await expect(api.getPublicEquipment(1)).resolves.toEqual(equipment);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/public/equipment', '/api/public/equipment/1']);
  });

  it.each([0, 1, 4, Number.MAX_SAFE_INTEGER])('preserves a valid active reservation count in catalogue and detail: %s', async (active_reservations_count) => {
    const product = { ...equipment, active_reservations_count };
    fetchMock.mockResolvedValueOnce(Response.json([product])).mockResolvedValueOnce(Response.json(product));
    await expect(api.listPublicEquipment()).resolves.toEqual([product]);
    await expect(api.getPublicEquipment(1)).resolves.toEqual(product);
  });

  it.each([undefined, null, -1, 1.5, '4', true, {}, [], Number.MAX_SAFE_INTEGER + 1])(
    'rejects a missing or malformed active reservation count in catalogue and detail: %j', async (active_reservations_count) => {
      const product = { ...equipment, active_reservations_count };
      fetchMock.mockResolvedValueOnce(Response.json([product])).mockResolvedValueOnce(Response.json(product));
      await expect(api.listPublicEquipment()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
      await expect(api.getPublicEquipment(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
    },
  );

  it.each([
    null,
    { ...equipment, code: 'PRIVATE-CODE' },
    { ...equipment, description: 'PRIVATE-NOTES' },
    { ...equipment, id: 0 },
    { ...equipment, technical_specs: ['4K'] },
    { ...equipment, technical_specs: { Resolución: 4000 } },
    { ...equipment, image_url: 'javascript:alert(1)' },
    { ...equipment, image_url: '//other.test/image.svg' },
    { ...equipment, image_url: 'https://user:secret@other.test/image.svg' },
    { ...equipment, image_url: '/api/public/images/../private.svg' },
    { ...equipment, image_url: 'https://other.test/image.svg?token=private' },
    { ...equipment, image_fallback_url: 'https://other.test/fallback.svg' },
  ])('rejects malformed or private catalogue responses: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getPublicEquipment(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each(['/api/public/images/cameras/aurora.svg', 'https://images.example.test/aurora.jpg', 'HTTPS://images.example.test/aurora.jpg'])(
    'accepts an optional safe image while preserving the local alternative: %s', async (image_url) => {
      fetchMock.mockResolvedValue(Response.json({ ...equipment, image_url }));
      await expect(api.getPublicEquipment(1)).resolves.toMatchObject({ image_url, image_fallback_url: equipment.image_fallback_url });
      expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1', expect.any(Object));
    },
  );

  it('requires a select-dates state when dates are absent and forwards complete days without times', async () => {
    const pending = { equipment_id: 1, start_date: null, end_date: null, available: null, status: 'select_dates' };
    fetchMock.mockResolvedValueOnce(Response.json(pending)).mockResolvedValueOnce(Response.json(availability));
    await expect(api.getPublicAvailability(1)).resolves.toEqual(pending);
    await expect(api.getPublicAvailability(1, dates)).resolves.toEqual(availability);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/public/equipment/1/availability',
      '/api/public/equipment/1/availability?start_date=2026-11-10&end_date=2026-11-12',
    ]);
  });

  it.each([
    { ...availability, available: false },
    { ...availability, status: 'unavailable' },
    { ...availability, status: 'select_dates' },
    { ...availability, start_date: null },
    { ...availability, start_date: '2026-11-31' },
    { ...availability, start_date: '2027-02-29' },
    { ...availability, start_date: '2026-11-10T00:00:00' },
    { ...availability, end_date: '2026-11-10' },
    { ...availability, end_date: '2026-11-09' },
    { ...availability, reason: 'blocking_incident' },
    { ...availability, conflicting_reservation_ids: [31] },
  ])('rejects inconsistent availability or leaked private reasons: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getPublicAvailability(1, dates)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('preserves an unavailable result without exposing the underlying cause', async () => {
    fetchMock.mockResolvedValue(Response.json({ ...availability, available: false, status: 'unavailable' }));
    await expect(api.getPublicAvailability(1, dates)).resolves.toMatchObject({ available: false, status: 'unavailable' });
  });

  it('reads the date-only public calendar with bounded ranges and no private projection or CSRF', async () => {
    const controller = new AbortController();
    const calendar = { equipment_id: 1, ...dates, occupied_ranges: [dates], can_book: true };
    fetchMock.mockResolvedValueOnce(Response.json(calendar));
    await expect(api.getPublicAvailabilityCalendar(1, dates, controller.signal)).resolves.toEqual(calendar);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/calendar?start_date=2026-11-10&end_date=2026-11-12', expect.objectContaining({ signal: controller.signal, credentials: 'same-origin' }));
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('queries eligible return dates from the selected pickup without exposing physical unit details', async () => {
    const calendar = { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-11'] };
    fetchMock.mockResolvedValueOnce(Response.json(calendar));
    await expect(api.getPublicAvailabilityCalendar(1, { ...dates, booking_start: '2026-11-09' })).resolves.toEqual(calendar);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/calendar?start_date=2026-11-10&end_date=2026-11-12&booking_start=2026-11-09', expect.any(Object));
  });

  it('reads public reservation dates with the requested signal, same origin and no CSRF', async () => {
    const controller = new AbortController();
    const response = { equipment_id: 1, reservations: [dates] };
    fetchMock.mockResolvedValueOnce(Response.json(response));
    await expect(api.getPublicReservationDates(1, controller.signal)).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/1/reservations', expect.objectContaining({ signal: controller.signal, credentials: 'same-origin' }));
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('accepts an empty reservation list and a canonical model id for another unit', async () => {
    const response = { equipment_id: 1, reservations: [] };
    fetchMock.mockResolvedValueOnce(Response.json(response));
    await expect(api.getPublicReservationDates(9)).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/public/equipment/9/reservations', expect.objectContaining({ signal: null }));
  });

  it('preserves duplicate and overlapping original reservation intervals without bounding them to the calendar window', async () => {
    const response = { equipment_id: 1, reservations: [
      { start_date: '2024-02-29', end_date: '2028-12-31' },
      dates, dates,
      { start_date: '2026-11-11', end_date: '2026-11-14' },
      { start_date: '2075-01-01', end_date: '2075-01-03' },
    ] };
    fetchMock.mockResolvedValueOnce(Response.json(response));
    await expect(api.getPublicReservationDates(1)).resolves.toEqual(response);
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
    { equipment_id: 1, reservations: [{ start_date: dates.start_date }] },
    { equipment_id: 1, reservations: [{ start_date: null, end_date: dates.end_date }] },
    { equipment_id: 1, reservations: [{ start_date: '2026-11-31', end_date: '2026-12-02' }] },
    { equipment_id: 1, reservations: [{ start_date: '2027-02-29', end_date: '2027-03-02' }] },
    { equipment_id: 1, reservations: [{ start_date: '2026-11-10T00:00:00', end_date: dates.end_date }] },
    { equipment_id: 1, reservations: [{ start_date: dates.start_date, end_date: dates.start_date }] },
    { equipment_id: 1, reservations: [{ start_date: dates.end_date, end_date: dates.start_date }] },
    { equipment_id: 1, reservations: [], customer_name: 'Private' },
    { equipment_id: 1, reservations: [{ ...dates, id: 31 }] },
    { equipment_id: 1, reservations: [{ ...dates, equipment_id: 7 }] },
    { equipment_id: 1, reservations: [{ ...dates, customer_email: 'private@example.test' }] },
    { equipment_id: 1, reservations: [{ ...dates, status: 'confirmed' }] },
  ])('rejects malformed or private reservation date data: %j', async (response) => {
    fetchMock.mockResolvedValueOnce(Response.json(response));
    await expect(api.getPublicReservationDates(1)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('preserves an aborted public reservation date request', async () => {
    const controller = new AbortController();
    controller.abort();
    const failure = new DOMException('Aborted', 'AbortError');
    fetchMock.mockRejectedValueOnce(failure);
    await expect(api.getPublicReservationDates(1, controller.signal)).rejects.toBe(failure);
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  it('does not invalidate the account or current CSRF token for a public reservation date 401', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToUnauthorized(listener);
    try {
      fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'current-token' }))
        .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }))
        .mockResolvedValueOnce(Response.json({ detail: 'Error público.' }, { status: 401 }))
        .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }));
      await api.cancelMyReservation(31);
      await expect(api.getPublicReservationDates(1)).rejects.toMatchObject({ status: 401 });
      await api.cancelMyReservation(31);
      expect(listener).not.toHaveBeenCalled();
      expect(fetchMock.mock.calls.filter(([path]) => path === '/api/auth/csrf')).toHaveLength(1);
    } finally { unsubscribe(); }
  });

  it.each([
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, customer_name: 'Private' },
    { equipment_id: 1, ...dates, occupied_ranges: [{ ...dates, reservation_id: 31 }], can_book: true },
    { equipment_id: 1, ...dates, occupied_ranges: [{ ...dates, customer_email: 'private@example.test' }], can_book: true },
    { equipment_id: 1, ...dates, occupied_ranges: [{ start_date: '2026-11-09', end_date: '2026-11-12' }], can_book: true },
    { equipment_id: 1, ...dates, occupied_ranges: [{ start_date: '2026-11-10', end_date: '2026-11-13' }], can_book: true },
    { equipment_id: 1, ...dates, occupied_ranges: [{ start_date: '2026-11-10', end_date: '2026-11-10' }], can_book: true },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: 'true' },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, reason: 'Private incident' },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-09'] },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-12'] },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: ['2026-11-31'] },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: [{ equipment_id: 2 }] },
    { equipment_id: 1, ...dates, occupied_ranges: [], can_book: true, unavailable_end_dates: null },
  ])('rejects private or inconsistent calendar data: %j', async (calendar) => {
    fetchMock.mockResolvedValueOnce(Response.json(calendar));
    await expect(api.getPublicAvailabilityCalendar(1, dates)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('does not invalidate the authenticated session for an unexpected public 401', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToUnauthorized(listener);
    try {
      fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'current-token' }))
        .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }))
        .mockResolvedValueOnce(Response.json({ detail: 'Error público.' }, { status: 401 }))
        .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }));
      await api.cancelMyReservation(31);
      await expect(api.listPublicEquipment()).rejects.toMatchObject({ status: 401 });
      await api.cancelMyReservation(31);
      expect(listener).not.toHaveBeenCalled();
      expect(fetchMock.mock.calls.filter(([path]) => path === '/api/auth/csrf')).toHaveLength(1);
    } finally { unsubscribe(); }
  });

  it('keeps a catalogue read usable when the account changes while it is loading', async () => {
    let resolveCatalogue: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation((path) => {
      if (path === '/api/public/equipment') return new Promise((resolve) => { resolveCatalogue = resolve; });
      return Promise.resolve(Response.json(path === '/api/auth/csrf' ? { csrf_token: 'new-token' } : session));
    });
    const pending = api.listPublicEquipment();
    await api.login({ username: 'cliente@example.test', password: 'sólo prueba' });
    resolveCatalogue?.(Response.json([equipment]));
    await expect(pending).resolves.toEqual([equipment]);
  });
});

describe('customer API', () => {
  it('sends an optional stable idempotency key separately from the allowed booking fields', async () => {
    const key = 'a26af448-f231-4ac7-9d8b-9794d2ae7541';
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(reservation, { status: 201 }))
      .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }, { status: 201 }));
    await expect(api.createMyReservation({ equipment_id: 1, ...dates }, key)).resolves.toEqual(reservation);
    await expect(api.createMyReservation({ equipment_id: 1, ...dates }, key)).resolves.toMatchObject({ id: 31, status: 'cancelled' });
    for (const [, options] of fetchMock.mock.calls.slice(1)) {
      expect(new Headers(options?.headers).get('Idempotency-Key')).toBe(key);
      expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('customer-token');
      expect(JSON.parse(options?.body as string)).toEqual({ equipment_id: 1, ...dates });
    }
  });
  it('lists and reads only the /me projection, keeping response bodies free of identity fields', async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValueOnce(Response.json([reservation])).mockResolvedValueOnce(Response.json(reservation))
      .mockResolvedValueOnce(Response.json([incident])).mockResolvedValueOnce(Response.json(incident));
    await expect(api.listMyReservations(controller.signal)).resolves.toEqual([reservation]);
    await expect(api.getMyReservation(31, controller.signal)).resolves.toEqual(reservation);
    await expect(api.listMyIncidents(controller.signal)).resolves.toEqual([incident]);
    await expect(api.getMyIncident(8, controller.signal)).resolves.toEqual(incident);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/me/reservations', '/api/me/reservations/31', '/api/me/incidents', '/api/me/incidents/8',
    ]);
    expect(fetchMock.mock.calls.every(([, options]) => options?.credentials === 'same-origin' && options.signal === controller.signal)).toBe(true);
  });

  it('creates a booking with only the allowed equipment and date fields using CSRF', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(reservation, { status: 201 }));
    const input = { equipment_id: 1, ...dates, customer_id: 99, status: 'cancelled', customer_email: 'other@example.test' };
    await expect(api.createMyReservation(input)).resolves.toEqual(reservation);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/auth/csrf', '/api/me/reservations']);
    const options = fetchMock.mock.calls[1]?.[1];
    expect(options).toMatchObject({ method: 'POST', body: JSON.stringify({ equipment_id: 1, ...dates }), credentials: 'same-origin' });
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('customer-token');
  });

  it('cancels without sending fields and preserves the returned cancellation history', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }));
    await expect(api.cancelMyReservation(31)).resolves.toMatchObject({ ...dates, status: 'cancelled' });
    expect(fetchMock.mock.calls[1]).toEqual(['/api/me/reservations/31/cancel', expect.objectContaining({ method: 'POST' })]);
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBeUndefined();
  });

  it('reports an incident by reservation with only the customer title and description', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json(incident, { status: 201 }));
    const input = { title: incident.title, description: incident.description, blocking: true };
    await expect(api.createMyIncident(31, input)).resolves.toEqual(incident);
    expect(fetchMock.mock.calls[1]).toEqual(['/api/me/reservations/31/incidents', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ title: incident.title, description: incident.description }),
    })]);
  });

  it.each([
    { ...reservation, customer_name: 'Private identity' },
    { ...reservation, customer_user_id: 99 },
    { ...reservation, status: 'pending' },
    { ...reservation, start_date: '2026-02-30' },
    { ...reservation, end_date: reservation.start_date },
  ])('rejects incompatible or broader private reservation schemas: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getMyReservation(31)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each([
    { ...incident, internal_notes: 'Private management note' },
    { ...incident, resolution: 'Internal resolution' },
    { ...incident, blocking: true },
    { ...incident, reservation_id: null },
    { ...incident, public_response: null },
  ])('rejects incompatible or broader private incident schemas: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getMyIncident(8)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('preserves a booking conflict without retrying or creating another reservation', async () => {
    const message = 'La disponibilidad ha cambiado. Consulta otra vez y elige otro intervalo.';
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ detail: message }, { status: 409 }));
    await expect(api.createMyReservation({ equipment_id: 1, ...dates })).rejects.toMatchObject({ status: 409, message });
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/me/reservations')).toHaveLength(1);
  });

  it('returns field validation errors for the incident form', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'customer-token' }))
      .mockResolvedValueOnce(Response.json({ detail: [{ loc: ['body', 'title'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.createMyIncident(31, { title: '', description: incident.description }))
      .rejects.toMatchObject({ status: 422, fields: { title: 'Este campo es obligatorio.' } });
  });

  it('invalidates the session for a private 401 and retains 403 and 404 errors', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToUnauthorized(listener);
    try {
      for (const status of [404, 403, 401]) {
        fetchMock.mockResolvedValueOnce(Response.json({ detail: 'Recurso no disponible.' }, { status }));
        await expect(api.getMyReservation(31)).rejects.toMatchObject({ status });
      }
      expect(listener).toHaveBeenCalledTimes(1);
    } finally { unsubscribe(); }
  });

  it('never presents a previous account’s pending reservation list after a new login', async () => {
    let resolveOldAccount: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation((path) => {
      if (path === '/api/me/reservations') return new Promise((resolve) => { resolveOldAccount = resolve; });
      return Promise.resolve(Response.json(path === '/api/auth/csrf' ? { csrf_token: 'new-token' } : session));
    });
    const pending = api.listMyReservations();
    await api.login({ username: 'cliente@example.test', password: 'sólo prueba' });
    resolveOldAccount?.(Response.json([reservation]));
    await expect(pending).rejects.toMatchObject({ status: 401 });
  });

  it('obtains fresh CSRF after a rejected write without automatically repeating it', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'old-token' }))
      .mockResolvedValueOnce(Response.json({ detail: 'CSRF no válido.' }, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ csrf_token: 'new-token' }))
      .mockResolvedValueOnce(Response.json({ ...reservation, status: 'cancelled' }));
    await expect(api.cancelMyReservation(31)).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await api.cancelMyReservation(31);
    expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get('X-CSRF-Token')).toBe('new-token');
  });
});
