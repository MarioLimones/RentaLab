import { expect, it, vi } from 'vitest';
import { api, limpiarTokenCsrf } from './cliente';

it("conserva las rutas de validación del servidor como errores de campo en español sin perder el estado", async () => {
  limpiarTokenCsrf();
  const respuestaValidacion = Response.json({ detail: [
    { loc: ['body', 'name'], msg: 'Field required', type: 'missing' },
    { loc: ['body', 'code'], msg: 'String should match pattern', type: 'string_pattern_mismatch' },
  ] }, { status: 422 });
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((ruta) => Promise.resolve(
    ruta === '/api/auth/csrf' ? Response.json({ csrf_token: 'test-csrf' }) : respuestaValidacion,
  )));
  await expect(api.crearEquipo({ code: '', name: '', category: '', description: '', active: true }))
    .rejects.toMatchObject({ estado: 422, campos: { name: 'Este campo es obligatorio.', code: 'Revisa el formato de este campo.' } });
});

it("muestra un error de campo útil cuando la respuesta de autenticación omite el contexto de validación", async () => {
  limpiarTokenCsrf();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation((ruta) => Promise.resolve(Response.json(
    ruta === '/api/auth/csrf' ? { csrf_token: 'test-csrf' }
      : { detail: [{ loc: ['body', 'password'], msg: 'String should have at most 1024 characters', type: 'string_too_long' }] },
    { status: ruta === '/api/auth/csrf' ? 200 : 422 },
  ))));
  await expect(api.iniciarSesion({ username: 'operador', password: 'ficticia' }))
    .rejects.toMatchObject({ estado: 422, campos: { password: 'El valor supera la longitud permitida.' } });
});
