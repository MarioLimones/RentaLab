import { beforeEach, expect, it, vi } from 'vitest';
import { api, clearCsrfToken } from './client';

const equipment = {
  id: 1, code: 'CAM-001', name: 'Cámara', category: 'Vídeo', description: 'Nota privada', active: true,
  public_description: 'Ficha pública', technical_specs: { Sensor: 'APS-C' }, image_url: null,
};
const reservation = {
  id: 1, equipment_id: 1, customer_name: 'Alicia', customer_email: 'alicia@example.test',
  start_date: '2030-11-10', end_date: '2030-11-12', status: 'confirmed', external_reference: null,
  customer_user_id: 3, origin: 'portal',
};
const incident = {
  id: 2, equipment_id: 1, title: 'Aviso', description: 'Problema comunicado', priority: 'medium',
  blocking: false, status: 'open', resolution: '', confirmed_reservation_ids: [1], warning: null,
  reservation_id: 1, author_user_id: 3, public_response: 'Estamos revisándolo', internal_notes: 'Nota privada',
};
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  clearCsrfToken();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', (path: RequestInfo | URL, options?: RequestInit) => path === '/api/auth/csrf'
    ? Promise.resolve(Response.json({ csrf_token: 'test-token' })) : fetchMock(path, options));
});

it('preserva características públicas de gestión y el origen/propietario administrativos', async () => {
  fetchMock.mockResolvedValueOnce(Response.json(equipment)).mockResolvedValueOnce(Response.json([reservation]));
  expect(await api.getEquipment(1)).toEqual(equipment);
  expect(await api.listReservations({ customer: 'María_%', customer_user_id: 3, origin: 'portal', status: 'confirmed' })).toEqual([reservation]);
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/reservations?customer=Mar%C3%ADa_%25&customer_user_id=3&origin=portal&status=confirmed');
});

it('acepta el esquema HTTPS en mayúsculas conservado por el backend en detalle y listado', async () => {
  const serializedEquipment = { ...equipment, image_url: 'HTTPS://images.example.test/aurora.jpg' };
  fetchMock.mockResolvedValueOnce(Response.json(serializedEquipment)).mockResolvedValueOnce(Response.json([serializedEquipment]));
  await expect(api.getEquipment(1)).resolves.toEqual(serializedEquipment);
  await expect(api.listEquipment()).resolves.toEqual([serializedEquipment]);
});

it.each([
  { ...reservation, origin: 'guessed' }, { ...reservation, customer_user_id: 0 },
  { ...reservation, customer_user_id: '3' }, { ...equipment, technical_specs: { Sensor: 3 } },
  { ...equipment, image_url: 'javascript:alert(1)' }, { ...equipment, public_description: null },
])('rechaza nuevos campos administrativos mal formados: %j', async (value) => {
  fetchMock.mockResolvedValueOnce(Response.json(value));
  const action = 'code' in value ? api.getEquipment(1) : api.getReservation(1);
  await expect(action).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('edita comunicación y bloqueo con el cliente CSRF central y solo campos permitidos', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ ...incident, blocking: true }));
  const payload = {
    priority: 'high' as const, blocking: true, public_response: 'Revisión en curso', internal_notes: 'Comprobación interna',
    author_user_id: 99, reservation_id: 99, status: 'resolved',
  };
  await expect(api.patchIncident(2, payload)).resolves.toMatchObject({ blocking: true, author_user_id: 3 });
  const [path, options] = fetchMock.mock.calls[0]!;
  expect(path).toBe('/api/incidents/2');
  expect(options?.method).toBe('PATCH');
  expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
  expect(JSON.parse(String(options?.body))).toEqual({
    priority: 'high', blocking: true, public_response: 'Revisión en curso', internal_notes: 'Comprobación interna',
  });
});

it.each([
  { ...incident, reservation_id: -1 }, { ...incident, author_user_id: '3' },
  { ...incident, public_response: null }, { ...incident, internal_notes: [] },
])('rechaza comunicaciones de incidencia mal formadas: %j', async (value) => {
  fetchMock.mockResolvedValueOnce(Response.json(value));
  await expect(api.getIncident(2)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('proyecta el alta administrativa sin aceptar origen ni propietario desde React', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ ...reservation, origin: 'admin', customer_user_id: null }));
  const payload = { ...reservation, origin: 'csv', customer_user_id: 99 };
  await api.createReservation(payload);
  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
    equipment_id: 1, customer_name: 'Alicia', customer_email: 'alicia@example.test',
    start_date: '2030-11-10', end_date: '2030-11-12', external_reference: null,
  });
});
