import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, IMPORT_EXAMPLE_URL, clearCsrfToken } from './client';

const equipment = {
  id: 1,
  code: 'CAM-001',
  name: 'Cámara de estudio',
  category: 'Vídeo',
  description: 'Equipo ficticio',
  active: true,
};
const equipmentInput = {
  code: equipment.code,
  name: equipment.name,
  category: equipment.category,
  description: equipment.description,
  active: equipment.active,
};
const reservation = {
  id: 3,
  equipment_id: 1,
  customer_name: 'Cliente ficticio',
  customer_email: 'cliente@example.test',
  start_date: '2026-11-10',
  end_date: '2026-11-12',
  status: 'confirmed',
  external_reference: null,
};
const reservationInput = {
  equipment_id: reservation.equipment_id,
  customer_name: reservation.customer_name,
  customer_email: reservation.customer_email,
  start_date: reservation.start_date,
  end_date: reservation.end_date,
};
const availability = {
  equipment_id: 1,
  start_date: '2026-11-10',
  end_date: '2026-11-12',
  available: true,
  reason: null,
  conflicting_reservation_ids: [],
};
const incident = {
  id: 4,
  equipment_id: 1,
  title: 'Conector pendiente de revisar',
  description: 'Incidencia ficticia de demostración.',
  priority: 'medium',
  blocking: false,
  status: 'open',
  resolution: '',
  confirmed_reservation_ids: [],
  warning: null,
};
const acceptedImportRow = {
  line: 2,
  external_reference: 'PEDIDO-FICTICIO-001',
  status: 'accepted',
  reservation: { ...reservation, external_reference: 'PEDIDO-FICTICIO-001' },
  message: 'Reserva creada.',
};
const importReport = {
  totals: { total: 3, accepted: 1, already_imported: 1, rejected: 1 },
  rows: [
    acceptedImportRow,
    {
      line: 3,
      external_reference: 'PEDIDO-FICTICIO-002',
      status: 'already_imported',
      reservation: { ...reservation, id: 4, status: 'cancelled', external_reference: 'PEDIDO-FICTICIO-002' },
      message: 'La referencia ya se importó; se conserva su cancelación.',
    },
    {
      line: 4,
      external_reference: null,
      status: 'rejected',
      reservation: null,
      message: 'El equipo indicado no existe.',
    },
  ],
};
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  clearCsrfToken();
  fetchMock.mockReset();
  // Keep the original business-contract assertions; authentication is covered separately.
  vi.stubGlobal('fetch', (path: RequestInfo | URL, options?: RequestInit) => path === '/api/auth/csrf'
    ? Promise.resolve(Response.json({ csrf_token: 'test-csrf' })) : fetchMock(path, options));
});

describe('API client', () => {
  it('checks health on the same origin', async () => {
    fetchMock.mockResolvedValue(Response.json({ status: 'ok' }));
    await expect(api.health()).resolves.toEqual({ status: 'ok' });
    expect(fetchMock).toHaveBeenCalledWith('/health', expect.objectContaining({ headers: expect.any(Headers) }));
  });

  it('uses /api for the complete equipment contract', async () => {
    fetchMock.mockResolvedValueOnce(Response.json([equipment]));
    await expect(api.listEquipment()).resolves.toEqual([equipment]);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/equipment', expect.any(Object));

    fetchMock.mockResolvedValueOnce(Response.json(equipment));
    await expect(api.getEquipment(1)).resolves.toEqual(equipment);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/equipment/1', expect.any(Object));

    fetchMock.mockResolvedValueOnce(Response.json(equipment, { status: 201 }));
    await expect(api.createEquipment(equipmentInput)).resolves.toEqual(equipment);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/equipment', expect.objectContaining({ method: 'POST', body: JSON.stringify(equipmentInput) }));

    fetchMock.mockResolvedValueOnce(Response.json(equipment));
    await expect(api.updateEquipment(1, equipmentInput)).resolves.toEqual(equipment);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/equipment/1', expect.objectContaining({ method: 'PUT' }));

    fetchMock.mockResolvedValueOnce(Response.json({ ...equipment, active: false }));
    await expect(api.patchEquipment(1, { active: false })).resolves.toMatchObject({ active: false });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/equipment/1', expect.objectContaining({ method: 'PATCH', body: '{"active":false}' }));
  });

  it.each([
    ['health', { status: 'broken' }],
    ['listEquipment', [{ ...equipment, active: 'yes' }]],
  ] as const)('rejects invalid %s responses instead of trusting TypeScript', async (method, body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api[method]()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('rejects malformed JSON', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Error</html>'));
    await expect(api.health()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('keeps the HTTP status and server detail', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: 'El código ya existe.' }, { status: 409 }));
    const request = api.createEquipment(equipmentInput);
    await expect(request).rejects.toMatchObject({ name: 'ApiError', status: 409, message: 'El código ya existe.' });
    await expect(request).rejects.toBeInstanceOf(ApiError);
  });

  it('makes FastAPI validation details readable', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.createEquipment(equipmentInput)).rejects.toThrow('Field required');
  });

  it('handles an HTTP error with a non-JSON body', async () => {
    fetchMock.mockResolvedValue(new Response('Unavailable', { status: 503 }));
    await expect(api.health()).rejects.toMatchObject({ status: 503, message: 'No se pudo completar la petición (503).' });
  });

  it('explains a network failure', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(api.health()).rejects.toThrow('No se pudo conectar con el servidor. Comprueba que el backend está en marcha.');
  });

  it('preserves request cancellation', async () => {
    const aborted = new DOMException('Aborted', 'AbortError');
    fetchMock.mockRejectedValue(aborted);
    await expect(api.health(new AbortController().signal)).rejects.toBe(aborted);
  });

});

describe('reservation API client', () => {
  it('lists reservations without optional filters', async () => {
    fetchMock.mockResolvedValue(Response.json([reservation]));
    await expect(api.listReservations()).resolves.toEqual([reservation]);
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations', expect.any(Object));
  });

  it('serializes supported list filters with URLSearchParams', async () => {
    fetchMock.mockResolvedValue(Response.json([]));
    await expect(api.listReservations({
      equipment_id: 1,
      status: 'cancelled',
      start_date: '2026-11-10',
      end_date: '2026-11-12',
    })).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/reservations?equipment_id=1&status=cancelled&start_date=2026-11-10&end_date=2026-11-12',
      expect.any(Object),
    );
  });

  it('omits unspecified filters and leaves validation of an incomplete range to Python', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: 'Indica ambas fechas.' }, { status: 422 }));
    await expect(api.listReservations({ start_date: '2026-11-10' }))
      .rejects.toMatchObject({ status: 422, message: 'Indica ambas fechas.' });
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations?start_date=2026-11-10', expect.any(Object));
  });

  it('gets a reservation and preserves its optional external reference', async () => {
    const imported = { ...reservation, external_reference: 'FICTICIO-001' };
    fetchMock.mockResolvedValue(Response.json(imported));
    await expect(api.getReservation(3)).resolves.toEqual(imported);
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations/3', expect.any(Object));
  });

  it('creates a reservation with a JSON body and accepts an omitted reference', async () => {
    fetchMock.mockResolvedValue(Response.json(reservation, { status: 201 }));
    await expect(api.createReservation(reservationInput)).resolves.toEqual(reservation);
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations', expect.objectContaining({
      method: 'POST', body: JSON.stringify(reservationInput),
    }));
    const options = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json');
  });

  it('sends an explicit null external reference without transforming client data', async () => {
    fetchMock.mockResolvedValue(Response.json(reservation, { status: 201 }));
    const input = { ...reservationInput, external_reference: null };
    await api.createReservation(input);
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations', expect.objectContaining({ body: JSON.stringify(input) }));
  });

  it('cancels without sending a body and accepts the retained cancelled reservation', async () => {
    const cancelled = { ...reservation, status: 'cancelled' };
    fetchMock.mockResolvedValue(Response.json(cancelled));
    await expect(api.cancelReservation(3)).resolves.toEqual(cancelled);
    expect(fetchMock).toHaveBeenCalledWith('/api/reservations/3/cancel', expect.objectContaining({ method: 'POST' }));
    const options = fetchMock.mock.calls[0]?.[1];
    expect(options?.body).toBeUndefined();
    expect(new Headers(options?.headers).has('Content-Type')).toBe(false);
  });

  it('queries equipment availability with ISO range parameters', async () => {
    fetchMock.mockResolvedValue(Response.json(availability));
    await expect(api.getEquipmentAvailability(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .resolves.toEqual(availability);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/equipment/1/availability?start_date=2026-11-10&end_date=2026-11-12', expect.any(Object),
    );
  });

  it.each(['equipment_inactive', 'reservation_overlap'])(
    'preserves the server availability reason %s', async (reason) => {
      const blocked = { ...availability, available: false, reason, conflicting_reservation_ids: [3] };
      fetchMock.mockResolvedValue(Response.json(blocked));
      await expect(api.getEquipmentAvailability(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
        .resolves.toEqual(blocked);
    },
  );

  it('preserves business conflicts instead of deciding overlap in TypeScript', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: 'El equipo tiene una reserva incompatible.' }, { status: 409 }));
    await expect(api.createReservation(reservationInput))
      .rejects.toMatchObject({ status: 409, message: 'El equipo tiene una reserva incompatible.' });
  });

  it.each([
    { ...reservation, id: 0 },
    { ...reservation, equipment_id: 1.5 },
    { ...reservation, customer_name: null },
    { ...reservation, customer_email: 42 },
    { ...reservation, start_date: '10/11/2026' },
    { ...reservation, end_date: null },
    { ...reservation, status: 'pending' },
    { ...reservation, external_reference: 1 },
  ])('rejects an invalid reservation response: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getReservation(3)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('rejects a reservation list containing invalid records', async () => {
    fetchMock.mockResolvedValue(Response.json([reservation, { ...reservation, status: 'pending' }]));
    await expect(api.listReservations()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it.each([
    { ...availability, equipment_id: -1 },
    { ...availability, start_date: '2026-11-10T00:00:00' },
    { ...availability, end_date: 12 },
    { ...availability, available: 'yes' },
    { ...availability, reason: 'invented_reason' },
    { ...availability, conflicting_reservation_ids: '3' },
    { ...availability, conflicting_reservation_ids: [0] },
  ])('rejects an invalid availability response: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getEquipmentAvailability(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});

describe('incident API client', () => {
  it('lists incidents without optional filters', async () => {
    fetchMock.mockResolvedValue(Response.json([incident]));
    await expect(api.listIncidents()).resolves.toEqual([incident]);
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents', expect.any(Object));
  });

  it.each([true, false])('serializes incident filters including blocking=%s', async (blocking) => {
    fetchMock.mockResolvedValue(Response.json([]));
    await expect(api.listIncidents({ equipment_id: 1, status: 'in_progress', priority: 'high', blocking }))
      .resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/incidents?equipment_id=1&status=in_progress&priority=high&blocking=${String(blocking)}`,
      expect.any(Object),
    );
  });

  it('omits unspecified incident filters', async () => {
    fetchMock.mockResolvedValue(Response.json([incident]));
    await api.listIncidents({ blocking: false });
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents?blocking=false', expect.any(Object));
  });

  it('gets an incident and preserves the server reservation warning', async () => {
    const warned = { ...incident, blocking: true, confirmed_reservation_ids: [3], warning: 'Revisa la reserva confirmada 3.' };
    fetchMock.mockResolvedValue(Response.json(warned));
    await expect(api.getIncident(4)).resolves.toEqual(warned);
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents/4', expect.any(Object));
  });

  it('creates an incident while leaving optional defaults to Python', async () => {
    const input = { equipment_id: 1, title: incident.title };
    fetchMock.mockResolvedValue(Response.json(incident, { status: 201 }));
    await expect(api.createIncident(input)).resolves.toEqual(incident);
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents', expect.objectContaining({
      method: 'POST', body: JSON.stringify(input),
    }));
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Content-Type')).toBe('application/json');
  });

  it('sends all explicitly supplied incident fields without transforming them', async () => {
    const input = { equipment_id: 1, title: incident.title, description: 'Detalle ficticio.', priority: 'low' as const, blocking: false };
    fetchMock.mockResolvedValue(Response.json({ ...incident, ...input }, { status: 201 }));
    await expect(api.createIncident(input)).resolves.toMatchObject(input);
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents', expect.objectContaining({ body: JSON.stringify(input) }));
  });

  it.each(['open', 'in_progress', 'resolved'] as const)('sends a status target %s for server validation', async (status) => {
    fetchMock.mockResolvedValue(Response.json({ ...incident, status }));
    await expect(api.changeIncidentStatus(4, { status })).resolves.toMatchObject({ status });
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents/4/status', expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ status }),
    }));
  });

  it.each(['Conector reparado en la demostración.', null])('preserves the caller resolution payload %s', async (resolution) => {
    fetchMock.mockResolvedValue(Response.json({ ...incident, status: 'resolved', resolution: resolution ?? '' }));
    await api.changeIncidentStatus(4, { status: 'resolved', resolution });
    expect(fetchMock).toHaveBeenCalledWith('/api/incidents/4/status', expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ status: 'resolved', resolution }),
    }));
  });

  it('preserves a transition conflict returned by Python', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: 'La transición de estado no está permitida.' }, { status: 409 }));
    await expect(api.changeIncidentStatus(4, { status: 'open' }))
      .rejects.toMatchObject({ status: 409, message: 'La transición de estado no está permitida.' });
  });

  it('accepts blocking incidents as the server availability reason', async () => {
    const blocked = { ...availability, available: false, reason: 'blocking_incident' };
    fetchMock.mockResolvedValue(Response.json(blocked));
    await expect(api.getEquipmentAvailability(1, { start_date: '2026-11-10', end_date: '2026-11-12' }))
      .resolves.toEqual(blocked);
  });

  it.each([
    { ...incident, id: 0 },
    { ...incident, equipment_id: 1.5 },
    { ...incident, title: null },
    { ...incident, description: 42 },
    { ...incident, priority: 'urgent' },
    { ...incident, blocking: 'false' },
    { ...incident, status: 'cancelled' },
    { ...incident, resolution: null },
    { ...incident, confirmed_reservation_ids: '3' },
    { ...incident, confirmed_reservation_ids: [-1] },
    { ...incident, warning: false },
  ])('rejects an invalid incident response: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.getIncident(4)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('rejects a list containing an invalid incident', async () => {
    fetchMock.mockResolvedValue(Response.json([incident, { ...incident, status: 'invented' }]));
    await expect(api.listIncidents()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});

describe('reservation import API client', () => {
  it('exposes the relative example URL for a future download link', () => {
    expect(IMPORT_EXAMPLE_URL).toBe('/api/imports/example');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('uploads exactly one file as multipart without setting its boundary manually', async () => {
    const file = new File(['contenido CSV ficticio'], 'pedidos.csv', { type: 'text/csv' });
    fetchMock.mockResolvedValue(Response.json(importReport));
    await expect(api.importReservations(file)).resolves.toEqual(importReport);
    expect(fetchMock).toHaveBeenCalledWith('/api/imports', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }));
    const options = fetchMock.mock.calls[0]?.[1];
    const body = options?.body as FormData;
    expect(Array.from(body.keys())).toEqual(['file']);
    expect(body.get('file')).toBe(file);
    expect(new Headers(options?.headers).get('Accept')).toBe('application/json');
    expect(new Headers(options?.headers).has('Content-Type')).toBe(false);
  });

  it('keeps JSON content type for existing API requests after adding multipart', async () => {
    const file = new File(['datos ficticios'], 'pedidos.csv');
    fetchMock.mockResolvedValueOnce(Response.json(importReport));
    await api.importReservations(file);
    fetchMock.mockResolvedValueOnce(Response.json(reservation, { status: 201 }));
    await api.createReservation(reservationInput);
    const options = fetchMock.mock.calls[1]?.[1];
    expect(options?.body).toBe(JSON.stringify(reservationInput));
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json');
  });

  it('returns a mixed report including rejected rows and a previously cancelled reservation', async () => {
    fetchMock.mockResolvedValue(Response.json(importReport, { status: 200 }));
    await expect(api.importReservations(new File(['datos ficticios'], 'pedidos.csv')))
      .resolves.toEqual(importReport);
  });

  it('accepts a report with no imported rows', async () => {
    const empty = { totals: { total: 0, accepted: 0, already_imported: 0, rejected: 0 }, rows: [] };
    fetchMock.mockResolvedValue(Response.json(empty));
    await expect(api.importReservations(new File(['cabecera CSV ficticia'], 'pedidos.csv')))
      .resolves.toEqual(empty);
  });

  it.each([
    [413, 'El archivo supera el tamaño permitido.'],
    [422, 'El archivo no contiene las columnas requeridas.'],
  ])('preserves global HTTP %s errors from Python', async (status, message) => {
    fetchMock.mockResolvedValue(Response.json({ detail: message }, { status }));
    await expect(api.importReservations(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toMatchObject({ name: 'ApiError', status, message });
  });

  it('keeps FastAPI validation details readable for multipart errors', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: [{ loc: ['body', 'file'], msg: 'Field required', type: 'missing' }] }, { status: 422 }));
    await expect(api.importReservations(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toThrow('Field required');
  });

  it.each([
    null,
    { ...importReport, totals: null },
    { ...importReport, totals: { ...importReport.totals, total: '3' } },
    { ...importReport, totals: { ...importReport.totals, accepted: -1 } },
    { ...importReport, totals: { ...importReport.totals, already_imported: 0.5 } },
    { ...importReport, totals: { ...importReport.totals, rejected: null } },
    { ...importReport, rows: {} },
    { ...importReport, rows: [{ ...acceptedImportRow, line: 0 }] },
    { ...importReport, rows: [{ ...acceptedImportRow, external_reference: 1 }] },
    { ...importReport, rows: [{ ...acceptedImportRow, status: 'pending' }] },
    { ...importReport, rows: [{ ...acceptedImportRow, reservation: { ...reservation, status: 'pending' } }] },
    { ...importReport, rows: [{ ...acceptedImportRow, reservation: null }] },
    { ...importReport, rows: [{ ...acceptedImportRow, status: 'already_imported', reservation: null }] },
    { ...importReport, rows: [{ ...acceptedImportRow, status: 'rejected' }] },
    { ...importReport, rows: [{ ...acceptedImportRow, message: null }] },
  ])('rejects an invalid import report: %j', async (body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(api.importReservations(new File(['datos ficticios'], 'pedidos.csv')))
      .rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});
