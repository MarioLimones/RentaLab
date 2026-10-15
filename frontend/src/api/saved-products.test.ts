import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, clearCsrfToken } from './client';

const fetchMock = vi.fn<typeof fetch>();
const dates = { start_date: '2027-11-17', end_date: '2027-11-20' };
const reservations = [1, 2].map((equipment_id) => ({ id: equipment_id + 40, equipment_id, ...dates, status: 'confirmed' }));

beforeEach(() => { clearCsrfToken(); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });

describe('saved products and joint reservation API', () => {
  it('replays a batch with its stable header and accepts current cancellation states without broadening the response schema', async () => {
    const key = '4be0ecae-7401-4ae6-ae23-8523e4aa4909';
    const response = [{ ...reservations[0], status: 'cancelled' }, reservations[1]];
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' }))
      .mockResolvedValueOnce(Response.json(response, { status: 201 }));
    await expect(api.createMyReservationsBatch({ equipment_ids: [11, 12], ...dates }, key)).resolves.toEqual(response);
    const options = fetchMock.mock.calls[1]![1];
    expect(new Headers(options?.headers).get('Idempotency-Key')).toBe(key);
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('joint-token');
    expect(JSON.parse(options?.body as string)).toEqual({ equipment_ids: [11, 12], ...dates });
  });

  it('requires a new unkeyed batch response to contain confirmed reservations', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' }))
      .mockResolvedValueOnce(Response.json([{ ...reservations[0], status: 'cancelled' }, reservations[1]]));
    await expect(api.createMyReservationsBatch({ equipment_ids: [11, 12], ...dates })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
    expect(new Headers(fetchMock.mock.calls[1]![1]?.headers).has('Idempotency-Key')).toBe(false);
  });
  it('reads saved model IDs without a CSRF round trip and uses the caller abort signal', async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(Response.json({ equipment_ids: [1, 2] }));
    await expect(api.listSavedProducts(controller.signal)).resolves.toEqual({ equipment_ids: [1, 2] });
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/me/saved-products', expect.objectContaining({ credentials: 'same-origin', signal: controller.signal }));
  });

  it.each([{ equipment_ids: [1, 1] }, { equipment_ids: [0] }, { equipment_ids: ['1'] }, { equipment_ids: [1], customer_id: 2 }, []])('rejects a malformed saved list: %j', async (value) => {
    fetchMock.mockResolvedValue(Response.json(value));
    await expect(api.listSavedProducts()).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });

  it('saves and removes with CSRF and accepts the canonical server list', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'saved-list-token' }))
      .mockResolvedValueOnce(Response.json({ equipment_ids: [1] })).mockResolvedValueOnce(Response.json({ equipment_ids: [] }));
    await expect(api.saveProduct(2)).resolves.toEqual({ equipment_ids: [1] });
    await expect(api.removeSavedProduct(1)).resolves.toEqual({ equipment_ids: [] });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/auth/csrf', '/api/me/saved-products/2', '/api/me/saved-products/1']);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('PUT');
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe('DELETE');
    for (const [, options] of fetchMock.mock.calls.slice(1)) expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('saved-list-token');
  });

  it('confirms all selected models in one authenticated POST and accepts assigned sibling units', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' })).mockResolvedValueOnce(Response.json(reservations, { status: 201 }));
    await expect(api.createMyReservationsBatch({ equipment_ids: [11, 12], ...dates })).resolves.toEqual(reservations);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/me/reservations/batch', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: JSON.stringify({ equipment_ids: [11, 12], ...dates }) }));
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('joint-token');
  });

  it.each([{ body: [reservations[0]] }, { body: [reservations[0], reservations[0]] }, { body: [{ ...reservations[0], end_date: '2027-11-21' }, reservations[1]] }])('rejects partial, duplicated or inconsistent confirmation: %j', async ({ body }) => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'joint-token' })).mockResolvedValueOnce(Response.json(body));
    await expect(api.createMyReservationsBatch({ equipment_ids: [1, 2], ...dates })).rejects.toThrow('El servidor devolvió una respuesta no válida.');
  });
});
