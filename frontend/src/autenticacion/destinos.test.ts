import { describe, expect, it } from 'vitest';
import { urlAcceso, destinoPermitido, destinoTrasAcceso } from './destinos';

describe("destinos seguros después del acceso", () => {
  it.each([
    null, '', 'https://other.example.test', '//other.example.test', '/\\other.example.test',
    'javascript:alert(1)', '/acceso?next=/admin', '/registro', '/api/me/reservations',
    '/admin/desconocido', '/equipos/nuevo', '/equipos/0', '/mis-reservas/0', '/catalogo\n',
  ])("rechaza destinos fuera de la lista de pantallas internas permitidas: %j", (valor) => {
    expect(destinoPermitido(valor)).toBeNull();
  });

  it.each([
    '/catalogo', '/mi-cuenta', '/mis-incidencias', '/mis-reservas', '/mis-reservas/31', '/equipos/1',
    '/admin', '/admin/equipos', '/admin/equipos/nuevo', '/admin/equipos/1', '/admin/equipos/1/editar',
    '/admin/reservas', '/admin/reservas/nueva', '/admin/reservas/31', '/admin/incidencias',
    '/admin/incidencias/nueva', '/admin/incidencias/8', '/admin/importaciones',
  ])("conserva una pantalla interna permitida: %s", (valor) => {
    expect(destinoPermitido(valor)).toBe(valor);
  });

  it("conserva las fechas del equipo y elimina parámetros y fragmentos arbitrarios", () => {
    expect(destinoPermitido('/equipos/1?start_date=2099-11-10&end_date=2099-11-12&redirect=https://other.test#private'))
      .toBe('/equipos/1?start_date=2099-11-10&end_date=2099-11-12');
  });

  it("rechaza fechas imposibles y conserva los filtros permitidos del catálogo", () => {
    expect(destinoPermitido('/equipos/1?start_date=0000-01-01&end_date=0000-01-02')).toBe('/equipos/1');
    expect(destinoPermitido('/catalogo?start_date=2099-02-29&end_date=2099-02-31&q=C%C3%A1mara&category=V%C3%ADdeo&available=1&role=admin'))
      .toBe('/catalogo?q=C%C3%A1mara&category=V%C3%ADdeo&available=1');
  });

  it("conserva días bisiestos válidos y elimina consultas de los destinos privados", () => {
    expect(destinoPermitido('/equipos/1?start_date=2096-02-29&end_date=2096-03-01'))
      .toBe('/equipos/1?start_date=2096-02-29&end_date=2096-03-01');
    expect(destinoPermitido('/mis-reservas/31?customer_id=99')).toBe('/mis-reservas/31');
    expect(destinoPermitido('/admin/reservas/nueva?equipment_id=4&role=customer')).toBe('/admin/reservas/nueva?equipment_id=4');
  });

  it("elige el destino según el rol devuelto por la sesión real", () => {
    expect(destinoTrasAcceso('customer', '/admin/importaciones')).toBe('/mi-cuenta');
    expect(destinoTrasAcceso('customer', '/mis-reservas/31')).toBe('/mis-reservas/31');
    expect(destinoTrasAcceso('admin', '/equipos/1')).toBe('/admin');
    expect(destinoTrasAcceso('admin', '/admin/importaciones')).toBe('/admin/importaciones');
    expect(destinoTrasAcceso('customer', 'https://other.test')).toBe('/mi-cuenta');
    expect(destinoTrasAcceso('admin', null)).toBe('/admin');
  });

  it("construye la URL de acceso únicamente con un destino codificado permitido", () => {
    const destino = '/equipos/1?start_date=2099-11-10&end_date=2099-11-12';
    expect(urlAcceso(destino)).toBe(`/acceso?next=${encodeURIComponent(destino)}`);
    expect(urlAcceso('//other.test')).toBe('/acceso');
  });
});
