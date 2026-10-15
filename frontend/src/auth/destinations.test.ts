import { describe, expect, it } from 'vitest';
import { accessUrl, allowedDestination, postLoginDestination } from './destinations';

describe('safe post-login destinations', () => {
  it.each([
    null, '', 'https://other.example.test', '//other.example.test', '/\\other.example.test',
    'javascript:alert(1)', '/acceso?next=/admin', '/registro', '/api/me/reservations',
    '/admin/desconocido', '/equipos/nuevo', '/equipos/0', '/mis-reservas/0', '/catalogo\n',
  ])('rejects destinations outside the internal screen allowlist: %j', (value) => {
    expect(allowedDestination(value)).toBeNull();
  });

  it.each([
    '/catalogo', '/mi-cuenta', '/mis-incidencias', '/mis-reservas', '/mis-reservas/31', '/equipos/1',
    '/admin', '/admin/equipos', '/admin/equipos/nuevo', '/admin/equipos/1', '/admin/equipos/1/editar',
    '/admin/reservas', '/admin/reservas/nueva', '/admin/reservas/31', '/admin/incidencias',
    '/admin/incidencias/nueva', '/admin/incidencias/8', '/admin/importaciones',
  ])('retains an allowed internal screen: %s', (value) => {
    expect(allowedDestination(value)).toBe(value);
  });

  it('preserves equipment dates but strips arbitrary query keys and fragments', () => {
    expect(allowedDestination('/equipos/1?start_date=2099-11-10&end_date=2099-11-12&redirect=https://other.test#private'))
      .toBe('/equipos/1?start_date=2099-11-10&end_date=2099-11-12');
  });

  it('rejects impossible dates while retaining permitted catalogue filters', () => {
    expect(allowedDestination('/equipos/1?start_date=0000-01-01&end_date=0000-01-02')).toBe('/equipos/1');
    expect(allowedDestination('/catalogo?start_date=2099-02-29&end_date=2099-02-31&q=C%C3%A1mara&category=V%C3%ADdeo&available=1&role=admin'))
      .toBe('/catalogo?q=C%C3%A1mara&category=V%C3%ADdeo&available=1');
  });

  it('preserves valid leap days and strips queries from private destinations', () => {
    expect(allowedDestination('/equipos/1?start_date=2096-02-29&end_date=2096-03-01'))
      .toBe('/equipos/1?start_date=2096-02-29&end_date=2096-03-01');
    expect(allowedDestination('/mis-reservas/31?customer_id=99')).toBe('/mis-reservas/31');
    expect(allowedDestination('/admin/reservas/nueva?equipment_id=4&role=customer')).toBe('/admin/reservas/nueva?equipment_id=4');
  });

  it('chooses the destination from the role returned by the real session', () => {
    expect(postLoginDestination('customer', '/admin/importaciones')).toBe('/mi-cuenta');
    expect(postLoginDestination('customer', '/mis-reservas/31')).toBe('/mis-reservas/31');
    expect(postLoginDestination('admin', '/equipos/1')).toBe('/admin');
    expect(postLoginDestination('admin', '/admin/importaciones')).toBe('/admin/importaciones');
    expect(postLoginDestination('customer', 'https://other.test')).toBe('/mi-cuenta');
    expect(postLoginDestination('admin', null)).toBe('/admin');
  });

  it('builds an access URL from only an allowed encoded destination', () => {
    const destination = '/equipos/1?start_date=2099-11-10&end_date=2099-11-12';
    expect(accessUrl(destination)).toBe(`/acceso?next=${encodeURIComponent(destination)}`);
    expect(accessUrl('//other.test')).toBe('/acceso');
  });
});
