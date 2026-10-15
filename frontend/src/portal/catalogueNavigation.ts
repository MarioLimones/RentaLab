import { allowedCatalogueDestination } from '../auth/destinations';
import type { DateRange } from '../types/api';
import { rangeSearch } from './dateRange';

const POSITION_KEY = 'rentalab.catalogue-position.v1';
export interface CatalogueReturn { path: string; top: number; }
let lastPosition: CatalogueReturn | null = null;

function position(value: unknown): CatalogueReturn | null {
  if (typeof value !== 'object' || value === null || !('path' in value) || !('top' in value)
    || typeof value.path !== 'string' || typeof value.top !== 'number'
    || !Number.isFinite(value.top) || value.top < 0 || value.top > 10_000_000) return null;
  const path = allowedCatalogueDestination(value.path);
  return path ? { path, top: value.top } : null;
}

function savedPosition(path: string): CatalogueReturn {
  try { lastPosition = position(JSON.parse(sessionStorage.getItem(POSITION_KEY) ?? 'null')); } catch { /* Storage can be unavailable. */ }
  return lastPosition?.path === path ? lastPosition : { path, top: 0 };
}

export function rememberCataloguePosition(path: string) {
  const safePath = allowedCatalogueDestination(path);
  if (!safePath) return;
  lastPosition = { path: safePath, top: Math.max(0, window.scrollY) };
  try { sessionStorage.setItem(POSITION_KEY, JSON.stringify(lastPosition)); } catch { /* Keep the position for this navigation in memory. */ }
}

export function catalogueProductPath(id: number, range: DateRange, cataloguePath: string): string {
  const query = new URLSearchParams(rangeSearch(range));
  const path = allowedCatalogueDestination(cataloguePath);
  // Plain/date-only URLs retain their existing shape. Other filters travel with the link,
  // including when it opens in another tab or passes through authentication.
  if (path && ['q', 'category', 'available'].some((key) => new URL(path, 'https://rentalab.invalid').searchParams.has(key))) query.set('catalogue', path);
  return `/equipos/${id}${query.size ? `?${query}` : ''}`;
}

export function productCatalogueReturn(state: unknown, parameter: string | null, fallback: string): CatalogueReturn {
  const fromState = typeof state === 'object' && state !== null && 'catalogueReturn' in state && typeof state.catalogueReturn === 'string'
    ? allowedCatalogueDestination(state.catalogueReturn) : null;
  const source = fromState ?? allowedCatalogueDestination(parameter) ?? allowedCatalogueDestination(fallback) ?? '/catalogo';
  const query = new URL(source, 'https://rentalab.invalid').searchParams;
  const dates = new URL(allowedCatalogueDestination(fallback) ?? '/catalogo', 'https://rentalab.invalid').searchParams;
  for (const field of ['start_date', 'end_date']) {
    query.delete(field);
    const value = dates.get(field);
    if (value) query.set(field, value);
  }
  const path = allowedCatalogueDestination(`/catalogo${query.size ? `?${query}` : ''}`) ?? '/catalogo';
  return savedPosition(path);
}

export function catalogueScrollTarget(path: string, state: unknown, isHistory: boolean): number | null {
  const safePath = allowedCatalogueDestination(path);
  if (!safePath) return null;
  const explicit = typeof state === 'object' && state !== null && 'catalogueRestore' in state ? position(state.catalogueRestore) : null;
  if (explicit?.path === safePath) return explicit.top;
  const previous = isHistory ? savedPosition(safePath) : null;
  return previous && previous.top > 0 ? previous.top : null;
}
