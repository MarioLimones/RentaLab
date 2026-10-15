import { beforeEach, describe, expect, it, vi } from 'vitest';
import { destinoPermitido } from '../autenticacion/destinos';
import { rutaProductoCatalogo, destinoDesplazamientoCatalogo, regresoCatalogoProducto, recordarPosicionCatalogo } from './navegacionCatalogo';

const fechas = { start_date: '2027-11-10', end_date: '2027-11-12' };
const catalogo = '/catalogo?start_date=2027-11-10&end_date=2027-11-12&q=Aurora&category=C%C3%A1maras&available=1';

beforeEach(() => { sessionStorage.clear(); });

describe("contexto de navegación del catálogo", () => {
  it("conserva los filtros del catálogo público en enlaces de producto y en el destino de acceso", () => {
    const producto = rutaProductoCatalogo(1, fechas, catalogo);
    const consulta = new URL(producto, 'https://rentalab.invalid').searchParams;
    expect(consulta.get('catalogue')).toBe(catalogo);
    expect(consulta.get('start_date')).toBe(fechas.start_date);
    expect(consulta.get('end_date')).toBe(fechas.end_date);
    expect(destinoPermitido(producto)).toBe(producto);
    expect(regresoCatalogoProducto(null, consulta.get('catalogue'), '/catalogo?start_date=2027-11-10&end_date=2027-11-12').path).toBe(catalogo);
  });

  it("recuerda el desplazamiento de una consulta sin cambios y sustituye solo las fechas cuando cambian", () => {
    vi.spyOn(window, 'scrollY', 'get').mockReturnValue(940);
    recordarPosicionCatalogo(catalogo);
    const original = regresoCatalogoProducto({ catalogueReturn: catalogo }, null, '/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    expect(original).toEqual({ path: catalogo, top: 940 });
    expect(destinoDesplazamientoCatalogo(catalogo, { catalogueRestore: original }, false)).toBe(940);
    expect(destinoDesplazamientoCatalogo(catalogo, null, true)).toBe(940);
    const cambiado = regresoCatalogoProducto({ catalogueReturn: catalogo }, null, '/catalogo?start_date=2027-11-11&end_date=2027-11-14');
    expect(cambiado).toEqual({ path: '/catalogo?start_date=2027-11-11&end_date=2027-11-14&q=Aurora&category=C%C3%A1maras&available=1', top: 0 });
    expect(regresoCatalogoProducto({ catalogueReturn: catalogo }, null, '/catalogo').path).toBe('/catalogo?q=Aurora&category=C%C3%A1maras&available=1');
  });

  it.each(['https://evil.test/catalogo', '//evil.test', '/admin', '/catalogo\\evil', '/catalogo\n', '/catalogo/../admin'])(
    "ignora rutas de retorno inseguras o ajenas al catálogo: %s", (ruta) => {
      expect(regresoCatalogoProducto({ catalogueReturn: ruta }, ruta, '/catalogo')).toEqual({ path: '/catalogo', top: 0 });
      expect(destinoPermitido(`/equipos/1?catalogue=${encodeURIComponent(ruta)}`)).toBe('/equipos/1');
    },
  );
});
