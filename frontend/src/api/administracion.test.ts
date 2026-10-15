import { beforeEach, expect, it, vi } from 'vitest';
import { api, limpiarTokenCsrf } from './cliente';

const equipo = {
  id: 1, code: 'CAM-001', name: 'Cámara', category: 'Vídeo', description: 'Nota privada', active: true,
  public_description: 'Ficha pública', technical_specs: { Sensor: 'APS-C' }, image_url: null,
};
const reserva = {
  id: 1, equipment_id: 1, customer_name: 'Alicia', customer_email: 'alicia@example.test',
  start_date: '2030-11-10', end_date: '2030-11-12', status: 'confirmed', external_reference: null,
  customer_user_id: 3, origin: 'portal',
};
const incidencia = {
  id: 2, equipment_id: 1, title: 'Aviso', description: 'Problema comunicado', priority: 'medium',
  blocking: false, status: 'open', resolution: '', confirmed_reservation_ids: [1], warning: null,
  reservation_id: 1, author_user_id: 3, public_response: 'Estamos revisándolo', internal_notes: 'Nota privada',
};
const peticionSimulada = vi.fn<typeof fetch>();

beforeEach(() => {
  limpiarTokenCsrf();
  peticionSimulada.mockReset();
  vi.stubGlobal('fetch', (ruta: RequestInfo | URL, opciones?: RequestInit) => ruta === '/api/auth/csrf'
    ? Promise.resolve(Response.json({ csrf_token: 'test-token' })) : peticionSimulada(ruta, opciones));
});

it('preserva características públicas de gestión y el origen/propietario administrativos', async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json(equipo)).mockResolvedValueOnce(Response.json([reserva]));
  expect(await api.obtenerEquipo(1)).toEqual(equipo);
  expect(await api.listarReservas({ customer: 'María_%', customer_user_id: 3, origin: 'portal', status: 'confirmed' })).toEqual([reserva]);
  expect(peticionSimulada.mock.calls[1]?.[0]).toBe('/api/reservations?customer=Mar%C3%ADa_%25&customer_user_id=3&origin=portal&status=confirmed');
});

it('acepta el esquema HTTPS en mayúsculas conservado por el backend en detalle y listado', async () => {
  const equipoSerializado = { ...equipo, image_url: 'HTTPS://images.example.test/aurora.jpg' };
  peticionSimulada.mockResolvedValueOnce(Response.json(equipoSerializado)).mockResolvedValueOnce(Response.json([equipoSerializado]));
  await expect(api.obtenerEquipo(1)).resolves.toEqual(equipoSerializado);
  await expect(api.listarEquipos()).resolves.toEqual([equipoSerializado]);
});

it.each([
  { ...reserva, origin: 'guessed' }, { ...reserva, customer_user_id: 0 },
  { ...reserva, customer_user_id: '3' }, { ...equipo, technical_specs: { Sensor: 3 } },
  { ...equipo, image_url: 'javascript:alert(1)' }, { ...equipo, public_description: null },
])('rechaza nuevos campos administrativos mal formados: %j', async (valor) => {
  peticionSimulada.mockResolvedValueOnce(Response.json(valor));
  const accion = 'code' in valor ? api.obtenerEquipo(1) : api.obtenerReserva(1);
  await expect(accion).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('edita comunicación y bloqueo con el cliente CSRF central y solo campos permitidos', async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ ...incidencia, blocking: true }));
  const datosSolicitud = {
    priority: 'high' as const, blocking: true, public_response: 'Revisión en curso', internal_notes: 'Comprobación interna',
    author_user_id: 99, reservation_id: 99, status: 'resolved',
  };
  await expect(api.modificarIncidencia(2, datosSolicitud)).resolves.toMatchObject({ blocking: true, author_user_id: 3 });
  const [ruta, opciones] = peticionSimulada.mock.calls[0]!;
  expect(ruta).toBe('/api/incidents/2');
  expect(opciones?.method).toBe('PATCH');
  expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('test-token');
  expect(JSON.parse(String(opciones?.body))).toEqual({
    priority: 'high', blocking: true, public_response: 'Revisión en curso', internal_notes: 'Comprobación interna',
  });
});

it.each([
  { ...incidencia, reservation_id: -1 }, { ...incidencia, author_user_id: '3' },
  { ...incidencia, public_response: null }, { ...incidencia, internal_notes: [] },
])('rechaza comunicaciones de incidencia mal formadas: %j', async (valor) => {
  peticionSimulada.mockResolvedValueOnce(Response.json(valor));
  await expect(api.obtenerIncidencia(2)).rejects.toThrow('El servidor devolvió una respuesta no válida.');
});

it('proyecta el alta administrativa sin aceptar origen ni propietario desde React', async () => {
  peticionSimulada.mockResolvedValueOnce(Response.json({ ...reserva, origin: 'admin', customer_user_id: null }));
  const datosSolicitud = { ...reserva, origin: 'csv', customer_user_id: 99 };
  await api.crearReserva(datosSolicitud);
  expect(JSON.parse(String(peticionSimulada.mock.calls[0]?.[1]?.body))).toEqual({
    equipment_id: 1, customer_name: 'Alicia', customer_email: 'alicia@example.test',
    start_date: '2030-11-10', end_date: '2030-11-12', external_reference: null,
  });
});
