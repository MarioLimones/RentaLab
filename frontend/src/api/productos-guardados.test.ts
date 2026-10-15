import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, limpiarTokenCsrf } from './cliente';

const peticionSimulada = vi.fn<typeof fetch>();
const fechas = { start_date: '2027-11-17', end_date: '2027-11-20' };
const reservas = [1, 2].map((id_equipo) => ({ id: id_equipo + 40, equipment_id: id_equipo, ...fechas, status: 'confirmed' }));

beforeEach(() => { limpiarTokenCsrf(); peticionSimulada.mockReset(); vi.stubGlobal('fetch', peticionSimulada); });

describe("API de productos guardados y reserva conjunta", () => {
  it("repite un lote con su cabecera estable y acepta cancelaciones actuales sin ampliar el esquema de respuesta", async () => {
    const key = '4be0ecae-7401-4ae6-ae23-8523e4aa4909';
    const respuesta = [{ ...reservas[0], status: 'cancelled' }, reservas[1]];
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' }))
      .mockResolvedValueOnce(Response.json(respuesta, { status: 201 }));
    await expect(api.crearMisReservasConjuntas({ equipment_ids: [11, 12], ...fechas }, key)).resolves.toEqual(respuesta);
    const opciones = peticionSimulada.mock.calls[1]![1];
    expect(new Headers(opciones?.headers).get('Idempotency-Key')).toBe(key);
    expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('joint-token');
    expect(JSON.parse(opciones?.body as string)).toEqual({ equipment_ids: [11, 12], ...fechas });
  });

  it("exige que una respuesta de lote nuevo sin clave contenga reservas confirmadas", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' }))
      .mockResolvedValueOnce(Response.json([{ ...reservas[0], status: 'cancelled' }, reservas[1]]));
    await expect(api.crearMisReservasConjuntas({ equipment_ids: [11, 12], ...fechas })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
    expect(new Headers(peticionSimulada.mock.calls[1]![1]?.headers).has('Idempotency-Key')).toBe(false);
  });
  it("consulta los identificadores de modelos guardados sin otra solicitud CSRF y usa la señal de cancelación recibida", async () => {
    const controlador = new AbortController();
    peticionSimulada.mockResolvedValue(Response.json({ equipment_ids: [1, 2] }));
    await expect(api.listarProductosGuardados(controlador.signal)).resolves.toEqual({ equipment_ids: [1, 2] });
    expect(peticionSimulada).toHaveBeenCalledExactlyOnceWith('/api/me/saved-products', expect.objectContaining({ credentials: 'same-origin', signal: controlador.signal }));
  });

  it.each([{ equipment_ids: [1, 1] }, { equipment_ids: [0] }, { equipment_ids: ['1'] }, { equipment_ids: [1], customer_id: 2 }, []])("rechaza una lista guardada mal formada: %j", async (valor) => {
    peticionSimulada.mockResolvedValue(Response.json(valor));
    await expect(api.listarProductosGuardados()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it("guarda y elimina con CSRF y acepta la lista canónica del servidor", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'saved-list-token' }))
      .mockResolvedValueOnce(Response.json({ equipment_ids: [1] })).mockResolvedValueOnce(Response.json({ equipment_ids: [] }));
    await expect(api.guardarProducto(2)).resolves.toEqual({ equipment_ids: [1] });
    await expect(api.eliminarProductoGuardado(1)).resolves.toEqual({ equipment_ids: [] });
    expect(peticionSimulada.mock.calls.map(([url]) => url)).toEqual(['/api/auth/csrf', '/api/me/saved-products/2', '/api/me/saved-products/1']);
    expect(peticionSimulada.mock.calls[1]?.[1]?.method).toBe('PUT');
    expect(peticionSimulada.mock.calls[2]?.[1]?.method).toBe('DELETE');
    for (const [, opciones] of peticionSimulada.mock.calls.slice(1)) expect(new Headers(opciones?.headers).get('X-CSRF-Token')).toBe('saved-list-token');
  });

  it("confirma todos los modelos seleccionados en un único POST autenticado y acepta unidades hermanas asignadas", async () => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' })).mockResolvedValueOnce(Response.json(reservas, { status: 201 }));
    await expect(api.crearMisReservasConjuntas({ equipment_ids: [11, 12], ...fechas })).resolves.toEqual(reservas);
    expect(peticionSimulada).toHaveBeenLastCalledWith('/api/me/reservations/batch', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: JSON.stringify({ equipment_ids: [11, 12], ...fechas }) }));
    expect(new Headers(peticionSimulada.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('joint-token');
  });

  it.each([{ body: [reservas[0]] }, { body: [reservas[0], reservas[0]] }, { body: [{ ...reservas[0], end_date: '2027-11-21' }, reservas[1]] }])("rechaza una confirmación parcial, duplicada o incoherente: %j", async ({ body: cuerpo }) => {
    peticionSimulada.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' })).mockResolvedValueOnce(Response.json(cuerpo));
    await expect(api.crearMisReservasConjuntas({ equipment_ids: [1, 2], ...fechas })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});
