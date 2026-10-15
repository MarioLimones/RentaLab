import { expect, it, vi } from 'vitest';
import { api, clearCsrfToken } from './client';

it('keeps server validation paths as Spanish field errors without losing status', async () => {
  clearCsrfToken();
  const validationResponse = Response.json({ detail: [
    { loc: ['body', 'name'], msg: 'Field required', type: 'missing' },
    { loc: ['body', 'code'], msg: 'String should match pattern', type: 'string_pattern_mismatch' },
  ] }, { status: 422 });
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((path) => Promise.resolve(
    path === '/api/auth/csrf' ? Response.json({ csrf_token: 'test-csrf' }) : validationResponse,
  )));
  await expect(api.createEquipment({ code: '', name: '', category: '', description: '', active: true }))
    .rejects.toMatchObject({ status: 422, fields: { name: 'Este campo es obligatorio.', code: 'Revisa el formato de este campo.' } });
});

it('shows a usable field error when the authentication response omits validation context', async () => {
  clearCsrfToken();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((path) => Promise.resolve(Response.json(
    path === '/api/auth/csrf' ? { csrf_token: 'test-csrf' }
      : { detail: [{ loc: ['body', 'password'], msg: 'String should have at most 1024 characters', type: 'string_too_long' }] },
    { status: path === '/api/auth/csrf' ? 200 : 422 },
  ))));
  await expect(api.login({ username: 'operador', password: 'ficticia' }))
    .rejects.toMatchObject({ status: 422, fields: { password: 'El valor supera la longitud permitida.' } });
});
