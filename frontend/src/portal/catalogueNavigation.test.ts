import { beforeEach, describe, expect, it, vi } from 'vitest';
import { allowedDestination } from '../auth/destinations';
import { catalogueProductPath, catalogueScrollTarget, productCatalogueReturn, rememberCataloguePosition } from './catalogueNavigation';

const dates = { start_date: '2027-11-10', end_date: '2027-11-12' };
const catalogue = '/catalogo?start_date=2027-11-10&end_date=2027-11-12&q=Aurora&category=C%C3%A1maras&available=1';

beforeEach(() => { sessionStorage.clear(); });

describe('catalogue navigation context', () => {
  it('carries public catalogue filters through product links and the login destination', () => {
    const product = catalogueProductPath(1, dates, catalogue);
    const query = new URL(product, 'https://rentalab.invalid').searchParams;
    expect(query.get('catalogue')).toBe(catalogue);
    expect(query.get('start_date')).toBe(dates.start_date);
    expect(query.get('end_date')).toBe(dates.end_date);
    expect(allowedDestination(product)).toBe(product);
    expect(productCatalogueReturn(null, query.get('catalogue'), '/catalogo?start_date=2027-11-10&end_date=2027-11-12').path).toBe(catalogue);
  });

  it('remembers the scroll for an unchanged result query and replaces only dates when they change', () => {
    vi.spyOn(window, 'scrollY', 'get').mockReturnValue(940);
    rememberCataloguePosition(catalogue);
    const original = productCatalogueReturn({ catalogueReturn: catalogue }, null, '/catalogo?start_date=2027-11-10&end_date=2027-11-12');
    expect(original).toEqual({ path: catalogue, top: 940 });
    expect(catalogueScrollTarget(catalogue, { catalogueRestore: original }, false)).toBe(940);
    expect(catalogueScrollTarget(catalogue, null, true)).toBe(940);
    const changed = productCatalogueReturn({ catalogueReturn: catalogue }, null, '/catalogo?start_date=2027-11-11&end_date=2027-11-14');
    expect(changed).toEqual({ path: '/catalogo?start_date=2027-11-11&end_date=2027-11-14&q=Aurora&category=C%C3%A1maras&available=1', top: 0 });
    expect(productCatalogueReturn({ catalogueReturn: catalogue }, null, '/catalogo').path).toBe('/catalogo?q=Aurora&category=C%C3%A1maras&available=1');
  });

  it.each(['https://evil.test/catalogo', '//evil.test', '/admin', '/catalogo\\evil', '/catalogo\n', '/catalogo/../admin'])(
    'ignores unsafe or non-catalogue return paths: %s', (path) => {
      expect(productCatalogueReturn({ catalogueReturn: path }, path, '/catalogo')).toEqual({ path: '/catalogo', top: 0 });
      expect(allowedDestination(`/equipos/1?catalogue=${encodeURIComponent(path)}`)).toBe('/equipos/1');
    },
  );
});
