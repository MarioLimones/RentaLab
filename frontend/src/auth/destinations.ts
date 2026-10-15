import type { UserRole } from '../types/api';

function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (!year) return false;
  const date = new Date(0);
  date.setUTCFullYear(year!, month! - 1, day!);
  return date.getUTCFullYear() === year && date.getUTCMonth() + 1 === month && date.getUTCDate() === day;
}

/** An allowlist, rather than an arbitrary URL supplied by the login query string. */
export function allowedDestination(raw: string | null): string | null {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\') || Array.from(raw).some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return null;
  const url = new URL(raw, 'https://rentalab.invalid');
  if (url.origin !== 'https://rentalab.invalid') return null;
  const path = url.pathname.replace(/\/$/, '') || '/';
  const admin = /^\/admin(?:\/(?:equipos(?:\/(?:nuevo|[1-9]\d*(?:\/editar)?))?|reservas(?:\/(?:nueva|[1-9]\d*))?|incidencias(?:\/(?:nueva|[1-9]\d*))?|importaciones))?$/.test(path);
  const customer = /^\/(?:catalogo|mi-lista|mi-cuenta|mis-incidencias|mis-reservas(?:\/[1-9]\d*)?|equipos\/[1-9]\d*)$/.test(path);
  if (!admin && !customer) return null;
  const query = new URLSearchParams();
  if (['/admin/reservas/nueva', '/admin/incidencias/nueva'].includes(path)) {
    const equipmentId = url.searchParams.get('equipment_id');
    if (equipmentId && /^[1-9]\d*$/.test(equipmentId)) query.set('equipment_id', equipmentId);
  }
  if (path === '/catalogo' || path === '/mi-lista' || /^\/equipos\/[1-9]\d*$/.test(path)) {
    for (const field of ['start_date', 'end_date']) {
      const value = url.searchParams.get(field);
      if (value && isCalendarDate(value)) query.set(field, value);
    }
    if (path === '/catalogo') {
      for (const field of ['q', 'category']) {
        const value = url.searchParams.get(field);
        if (value) query.set(field, value.slice(0, field === 'q' ? 120 : 80));
      }
      if (url.searchParams.get('available') === '1') query.set('available', '1');
    } else if (/^\/equipos\/[1-9]\d*$/.test(path)) {
      const catalogue = allowedCatalogueDestination(url.searchParams.get('catalogue'));
      if (catalogue) query.set('catalogue', catalogue);
    }
  }
  return path + (query.size ? `?${query}` : '');
}

/** Catalogue return links can carry filters, but never another screen or origin. */
export function allowedCatalogueDestination(raw: string | null): string | null {
  if (!raw || !/^\/catalogo(?:\?|$)/.test(raw)) return null;
  return allowedDestination(raw);
}

export function postLoginDestination(role: UserRole, raw: string | null): string {
  const destination = allowedDestination(raw);
  const administrative = destination === '/admin' || destination?.startsWith('/admin/');
  if (role === 'admin') return administrative && destination ? destination : '/admin';
  return destination && !administrative ? destination : '/mi-cuenta';
}

export function accessUrl(destination: string): string {
  const allowed = allowedDestination(destination);
  return '/acceso' + (allowed ? `?next=${encodeURIComponent(allowed)}` : '');
}
