import type {
  Equipment, EquipmentInput, EquipmentPatch, Reservation, ReservationInput, ReservationFilters, DateRange, Availability, Incident, IncidentInput, IncidentFilters, IncidentStatusChange, IncidentUpdate, ImportReport, ImportRowResult, ImportTotals, AuthSession, LoginInput, RegisterInput, User,
  PublicEquipment, PublicEquipmentFilters, PublicAvailability, PublicAvailabilityCalendar, PublicReservationDates, CustomerReservation, CustomerReservationInput, CustomerIncident, CustomerIncidentInput, SavedProducts, CustomerBatchReservationInput,
} from '../types/api';
export type * from '../types/api';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly fields: Record<string, string> = {}) {
    super(message);
    this.name = 'ApiError';
  }
}

const API_BASE = '/api';
export const IMPORT_EXAMPLE_URL = `${API_BASE}/imports/example`;
const INVALID_RESPONSE = 'El servidor devolvió una respuesta no válida.';
let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;
let csrfVersion = 0;
let sessionVersion = 0;
const unauthorizedListeners = new Set<() => void>();

// Tokens live only in memory. A rotated or expired session needs a new token.
export function clearCsrfToken() {
  csrfToken = null;
  csrfRequest = null;
  csrfVersion += 1;
}

function invalidateSession() {
  sessionVersion += 1;
  clearCsrfToken();
}

export function subscribeToUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => { unauthorizedListeners.delete(listener); };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isEquipment(value: unknown): value is Equipment {
  return isRecord(value)
    && typeof value.id === 'number' && Number.isInteger(value.id) && value.id > 0
    && typeof value.code === 'string'
    && typeof value.name === 'string'
    && typeof value.category === 'string'
    && typeof value.description === 'string'
    && (value.public_description === undefined || typeof value.public_description === 'string')
    && (value.technical_specs === undefined || isStringMap(value.technical_specs))
    && (value.image_url === undefined || value.image_url === null || isPublicImage(value.image_url))
    && typeof value.active === 'boolean';
}

function isStringMap(value: unknown): value is Record<string, string> {
  return isRecord(value) && Object.entries(value).every(([key, item]) => key.trim().length > 0 && typeof item === 'string');
}

function isEquipmentList(value: unknown): value is Equipment[] {
  return Array.isArray(value) && value.every(isEquipment);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function isCalendarDate(value: unknown): value is string {
  if (!isIsoDate(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year > 0 && month >= 1 && month <= 12 && day > 0 && day <= (days[month - 1] ?? 0);
}

function isDateRange(value: Record<string, unknown>): boolean {
  return isCalendarDate(value.start_date) && isCalendarDate(value.end_date) && value.end_date > value.start_date;
}

function isLocalPublicImage(value: unknown): value is string {
  const prefix = `${API_BASE}/public/images/`;
  return typeof value === 'string' && value.startsWith(prefix)
    && value.slice(prefix.length).split('/').every((segment) => /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*$/.test(segment));
}

function isPublicImage(value: unknown): value is string {
  if (isLocalPublicImage(value)) return true;
  if (typeof value !== 'string' || !/^https:\/\//i.test(value) || value.includes('\\')
    || Array.from(value).some((character) => character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname.length > 0 && !url.username && !url.password && !url.search && !url.hash;
  } catch {
    return false;
  }
}

function isPublicEquipment(value: unknown): value is PublicEquipment {
  return isRecord(value)
    && hasExactKeys(value, ['id', 'name', 'category', 'public_description', 'technical_specs', 'image_url', 'image_fallback_url', 'active_reservations_count'])
    && isPositiveInteger(value.id)
    && typeof value.name === 'string' && value.name.trim().length > 0
    && typeof value.category === 'string' && value.category.trim().length > 0
    && typeof value.public_description === 'string'
    && isRecord(value.technical_specs)
    && Object.entries(value.technical_specs).every(([key, item]) => key.trim().length > 0 && typeof item === 'string')
    && (value.image_url === null || isPublicImage(value.image_url))
    && isLocalPublicImage(value.image_fallback_url)
    && typeof value.active_reservations_count === 'number'
    && Number.isSafeInteger(value.active_reservations_count) && value.active_reservations_count >= 0;
}

function isPublicEquipmentList(value: unknown): value is PublicEquipment[] {
  return Array.isArray(value) && value.every(isPublicEquipment);
}

function isPublicAvailability(value: unknown): value is PublicAvailability {
  return isRecord(value)
    && hasExactKeys(value, ['equipment_id', 'start_date', 'end_date', 'available', 'status'])
    && isPositiveInteger(value.equipment_id)
    && ((value.status === 'select_dates' && value.start_date === null && value.end_date === null && value.available === null)
      || (isDateRange(value) && ((value.status === 'available' && value.available === true)
        || (value.status === 'unavailable' && value.available === false))));
}

function isPublicAvailabilityCalendar(value: unknown): value is PublicAvailabilityCalendar {
  return isRecord(value)
    && hasExactKeys(value, ['equipment_id', 'start_date', 'end_date', 'occupied_ranges', 'can_book', ...(Object.hasOwn(value, 'unavailable_end_dates') ? ['unavailable_end_dates'] : [])])
    && isPositiveInteger(value.equipment_id) && isDateRange(value)
    && typeof value.can_book === 'boolean'
    && (value.unavailable_end_dates === undefined || (Array.isArray(value.unavailable_end_dates)
      && value.unavailable_end_dates.every((date) => isCalendarDate(date)
        && typeof value.start_date === 'string' && typeof value.end_date === 'string'
        && date >= value.start_date && date < value.end_date)))
    && Array.isArray(value.occupied_ranges)
    && value.occupied_ranges.every((range) => isRecord(range)
      && hasExactKeys(range, ['start_date', 'end_date']) && isDateRange(range)
      && typeof range.start_date === 'string' && typeof range.end_date === 'string'
      && typeof value.start_date === 'string' && typeof value.end_date === 'string'
      && range.start_date >= value.start_date && range.end_date <= value.end_date);
}

function isPublicReservationDates(value: unknown): value is PublicReservationDates {
  return isRecord(value)
    && hasExactKeys(value, ['equipment_id', 'reservations'])
    && isPositiveInteger(value.equipment_id)
    && Array.isArray(value.reservations)
    && value.reservations.every((range) => isRecord(range)
      && hasExactKeys(range, ['start_date', 'end_date']) && isDateRange(range));
}

function isCustomerReservation(value: unknown): value is CustomerReservation {
  return isRecord(value)
    && hasExactKeys(value, ['id', 'equipment_id', 'start_date', 'end_date', 'status'])
    && isPositiveInteger(value.id) && isPositiveInteger(value.equipment_id)
    && isDateRange(value)
    && (value.status === 'confirmed' || value.status === 'cancelled');
}

function isCustomerReservationList(value: unknown): value is CustomerReservation[] {
  return Array.isArray(value) && value.every(isCustomerReservation);
}

function isSavedProducts(value: unknown): value is SavedProducts {
  return isRecord(value) && hasExactKeys(value, ['equipment_ids'])
    && Array.isArray(value.equipment_ids) && value.equipment_ids.every(isPositiveInteger)
    && new Set(value.equipment_ids).size === value.equipment_ids.length;
}

function isCustomerIncident(value: unknown): value is CustomerIncident {
  return isRecord(value)
    && hasExactKeys(value, ['id', 'reservation_id', 'title', 'description', 'status', 'public_response'])
    && isPositiveInteger(value.id) && isPositiveInteger(value.reservation_id)
    && typeof value.title === 'string' && typeof value.description === 'string'
    && (value.status === 'open' || value.status === 'in_progress' || value.status === 'resolved')
    && typeof value.public_response === 'string';
}

function isCustomerIncidentList(value: unknown): value is CustomerIncident[] {
  return Array.isArray(value) && value.every(isCustomerIncident);
}

function isReservation(value: unknown): value is Reservation {
  return isRecord(value)
    && isPositiveInteger(value.id)
    && isPositiveInteger(value.equipment_id)
    && typeof value.customer_name === 'string'
    && typeof value.customer_email === 'string'
    && isIsoDate(value.start_date)
    && isIsoDate(value.end_date)
    && (value.status === 'confirmed' || value.status === 'cancelled')
    && (value.customer_user_id === undefined || value.customer_user_id === null || isPositiveInteger(value.customer_user_id))
    && (value.origin === undefined || value.origin === 'portal' || value.origin === 'admin' || value.origin === 'csv' || value.origin === 'legacy')
    && (typeof value.external_reference === 'string' || value.external_reference === null);
}

function isReservationList(value: unknown): value is Reservation[] {
  return Array.isArray(value) && value.every(isReservation);
}

function isAvailability(value: unknown): value is Availability {
  return isRecord(value)
    && isPositiveInteger(value.equipment_id)
    && isIsoDate(value.start_date)
    && isIsoDate(value.end_date)
    && typeof value.available === 'boolean'
    && (value.reason === null || value.reason === 'equipment_inactive'
      || value.reason === 'reservation_overlap' || value.reason === 'blocking_incident')
    && Array.isArray(value.conflicting_reservation_ids)
    && value.conflicting_reservation_ids.every(isPositiveInteger);
}

function isIncident(value: unknown): value is Incident {
  return isRecord(value)
    && isPositiveInteger(value.id)
    && isPositiveInteger(value.equipment_id)
    && typeof value.title === 'string'
    && typeof value.description === 'string'
    && (value.priority === 'low' || value.priority === 'medium' || value.priority === 'high')
    && typeof value.blocking === 'boolean'
    && (value.status === 'open' || value.status === 'in_progress' || value.status === 'resolved')
    && typeof value.resolution === 'string'
    && (value.reservation_id === undefined || value.reservation_id === null || isPositiveInteger(value.reservation_id))
    && (value.author_user_id === undefined || value.author_user_id === null || isPositiveInteger(value.author_user_id))
    && (value.public_response === undefined || typeof value.public_response === 'string')
    && (value.internal_notes === undefined || typeof value.internal_notes === 'string')
    && Array.isArray(value.confirmed_reservation_ids)
    && value.confirmed_reservation_ids.every(isPositiveInteger)
    && (typeof value.warning === 'string' || value.warning === null);
}

function isIncidentList(value: unknown): value is Incident[] {
  return Array.isArray(value) && value.every(isIncident);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isImportTotals(value: unknown): value is ImportTotals {
  return isRecord(value)
    && isNonNegativeInteger(value.total)
    && isNonNegativeInteger(value.accepted)
    && isNonNegativeInteger(value.already_imported)
    && isNonNegativeInteger(value.rejected);
}

function isImportRowResult(value: unknown): value is ImportRowResult {
  return isRecord(value)
    && isPositiveInteger(value.line)
    && (typeof value.external_reference === 'string' || value.external_reference === null)
    && typeof value.message === 'string'
    && ((value.status === 'rejected' && value.reservation === null)
      || ((value.status === 'accepted' || value.status === 'already_imported') && isReservation(value.reservation)));
}

function isImportReport(value: unknown): value is ImportReport {
  return isRecord(value)
    && isImportTotals(value.totals)
    && Array.isArray(value.rows)
    && value.rows.every(isImportRowResult);
}

function queryString(parameters: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value !== undefined) search.set(key, String(value));
  }
  return search.size > 0 ? `?${search.toString()}` : '';
}

function isHealth(value: unknown): value is { status: 'ok' } {
  return isRecord(value) && value.status === 'ok';
}

function isAuthSession(value: unknown): value is AuthSession {
  return isRecord(value) && value.authenticated === true
    && typeof value.username === 'string' && value.username.length > 0
    && typeof value.expires_at === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(value.expires_at)
    && (value.role === 'customer' || value.role === 'admin')
    && (value.user === null ? value.role === 'admin'
      : isUser(value.user) && value.user.active && value.user.role === value.role);
}

function isUser(value: unknown): value is User {
  return isRecord(value) && isPositiveInteger(value.id)
    && typeof value.name === 'string' && value.name.length > 0
    && typeof value.email === 'string' && value.email.length > 0
    && (value.role === 'customer' || value.role === 'admin')
    && typeof value.active === 'boolean';
}

function isRegisteredCustomer(value: unknown): value is User {
  return isUser(value) && value.role === 'customer' && value.active;
}

function isCsrf(value: unknown): value is { csrf_token: string } {
  return isRecord(value) && typeof value.csrf_token === 'string' && value.csrf_token.length > 0;
}

function isSignedOut(value: unknown): value is { authenticated: false } {
  return isRecord(value) && value.authenticated === false;
}

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  // The first concurrent writes must share one anonymous session cookie.
  if (!csrfRequest) {
    const version = csrfVersion;
    const pending = request(`${API_BASE}/auth/csrf`, isCsrf, {}, false).then(({ csrf_token }) => {
      if (version !== csrfVersion) throw new ApiError('La protección de la sesión ha cambiado. Vuelve a intentarlo.', 403);
      csrfToken = csrf_token;
      return csrf_token;
    });
    csrfRequest = pending;
    void pending.finally(() => { if (csrfRequest === pending) csrfRequest = null; }).catch(() => {});
  }
  return csrfRequest;
}

function errorMessage(body: unknown, status: number): string {
  if (isRecord(body)) {
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      const messages = body.detail.flatMap((item: unknown) =>
        isRecord(item) && typeof item.msg === 'string' ? [item.msg] : [],
      );
      if (messages.length > 0) return messages.join(' ');
    }
  }
  return `No se pudo completar la petición (${status}).`;
}

function fieldErrors(body: unknown): Record<string, string> {
  if (!isRecord(body) || !Array.isArray(body.detail)) return {};
  const fields: Record<string, string> = {};
  for (const item of body.detail as unknown[]) {
    if (!isRecord(item) || !Array.isArray(item.loc)) continue;
    const field = item.loc.slice(1).find((part: unknown) => typeof part === 'string');
    if (typeof field !== 'string') continue;
    const context = isRecord(item.ctx) ? item.ctx : {};
    const message = typeof item.msg === 'string' ? item.msg.replace(/^Value error, /, '') : '';
    fields[field] = item.type === 'missing' ? 'Este campo es obligatorio.'
      : item.type === 'string_pattern_mismatch' ? 'Revisa el formato de este campo.'
        : item.type === 'string_too_long' ? typeof context.max_length === 'number'
          ? `Usa como máximo ${context.max_length} caracteres.` : 'El valor supera la longitud permitida.'
          : item.type === 'string_too_short' ? 'Escribe un valor con contenido.'
            : /^(El |La |Usa |Envía |Indica |Revisa )/.test(message) ? message
              : 'Revisa el valor de este campo.';
  }
  return fields;
}

async function request<T>(
  path: string,
  validate: (value: unknown) => value is T,
  options: RequestInit = {},
  notifyUnauthorized = true,
): Promise<T> {
  const version = sessionVersion;
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(options.method ?? 'GET')) {
    headers.set('X-CSRF-Token', await getCsrfToken());
  }
  ensureCurrentSession(path, version);

  let response: Response;
  try {
    response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  } catch (error) {
    if (isRecord(error) && error.name === 'AbortError') throw error;
    throw new ApiError('No se pudo conectar con el servidor. Comprueba que el backend está en marcha.', 0);
  }

  ensureCurrentSession(path, version);

  // Handle status even when an expired session response contains malformed JSON.
  if (response.status === 401 && version === sessionVersion && !isPublicPath(path)) {
    invalidateSession();
    if (notifyUnauthorized) for (const listener of unauthorizedListeners) listener();
  } else if (response.status === 403) {
    clearCsrfToken();
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(response.ok ? INVALID_RESPONSE : errorMessage(null, response.status), response.status);
  }

  if (!response.ok) throw new ApiError(errorMessage(body, response.status), response.status, fieldErrors(body));
  ensureCurrentSession(path, version);
  if (!validate(body)) throw new ApiError(INVALID_RESPONSE, response.status);
  return body;
}

function ensureCurrentSession(path: string, version: number) {
  if (path.startsWith(`${API_BASE}/`) && !isPublicPath(path) && version !== sessionVersion) {
    throw new ApiError('La sesión ha cambiado. Vuelve a intentarlo.', 401);
  }
}

function isPublicPath(path: string): boolean {
  return path.startsWith(`${API_BASE}/public/`);
}

export const api = {
  session: () => request(`${API_BASE}/auth/session`, isAuthSession, {}, false),
  register: (data: RegisterInput) => request(`${API_BASE}/auth/register`, isRegisteredCustomer, {
    method: 'POST', body: JSON.stringify(data),
  }, false),
  login: async (data: LoginInput) => {
    const session = await request(`${API_BASE}/auth/login`, isAuthSession, {
      method: 'POST', body: JSON.stringify(data),
    }, false);
    invalidateSession();
    return session;
  },
  logout: async () => {
    const result = await request(`${API_BASE}/auth/logout`, isSignedOut, { method: 'POST' });
    invalidateSession();
    return result;
  },
  health: (signal?: AbortSignal) => request('/health', isHealth, { signal: signal ?? null }),
  listPublicEquipment: (filters: PublicEquipmentFilters = {}, signal?: AbortSignal) => request(
    `${API_BASE}/public/equipment${queryString({ q: filters.q, category: filters.category })}`,
    isPublicEquipmentList, { signal: signal ?? null }, false,
  ),
  getPublicEquipment: (id: number, signal?: AbortSignal) => request(
    `${API_BASE}/public/equipment/${id}`, isPublicEquipment, { signal: signal ?? null }, false,
  ),
  getPublicAvailability: (id: number, dates?: DateRange, signal?: AbortSignal) => request(
    `${API_BASE}/public/equipment/${id}/availability${queryString({ start_date: dates?.start_date, end_date: dates?.end_date })}`,
    isPublicAvailability, { signal: signal ?? null }, false,
  ),
  getPublicAvailabilityCalendar: (id: number, dates: DateRange & { booking_start?: string }, signal?: AbortSignal) => request(
    `${API_BASE}/public/equipment/${id}/calendar${queryString({ start_date: dates.start_date, end_date: dates.end_date, booking_start: dates.booking_start })}`,
    isPublicAvailabilityCalendar, { signal: signal ?? null }, false,
  ),
  getPublicReservationDates: (id: number, signal?: AbortSignal) => request(
    `${API_BASE}/public/equipment/${id}/reservations`, isPublicReservationDates, { signal: signal ?? null }, false,
  ),
  listMyReservations: (signal?: AbortSignal) => request(
    `${API_BASE}/me/reservations`, isCustomerReservationList, { signal: signal ?? null },
  ),
  listSavedProducts: (signal?: AbortSignal) => request(
    `${API_BASE}/me/saved-products`, isSavedProducts, { signal: signal ?? null },
  ),
  saveProduct: (id: number) => request(`${API_BASE}/me/saved-products/${id}`, isSavedProducts, { method: 'PUT' }),
  removeSavedProduct: (id: number) => request(`${API_BASE}/me/saved-products/${id}`, isSavedProducts, { method: 'DELETE' }),
  createMyReservationsBatch: (data: CustomerBatchReservationInput, idempotencyKey?: string) => request(`${API_BASE}/me/reservations/batch`,
    (value): value is CustomerReservation[] => isCustomerReservationList(value)
      && value.length === data.equipment_ids.length && new Set(value.map((item) => item.id)).size === value.length
      && value.every((item) => (Boolean(idempotencyKey) || item.status === 'confirmed') && item.start_date === data.start_date && item.end_date === data.end_date),
    { method: 'POST', ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}), body: JSON.stringify({ equipment_ids: data.equipment_ids, start_date: data.start_date, end_date: data.end_date }) },
  ),
  getMyReservation: (id: number, signal?: AbortSignal) => request(
    `${API_BASE}/me/reservations/${id}`, isCustomerReservation, { signal: signal ?? null },
  ),
  createMyReservation: (data: CustomerReservationInput, idempotencyKey?: string) => request(`${API_BASE}/me/reservations`, isCustomerReservation, {
    method: 'POST', ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}),
    body: JSON.stringify({ equipment_id: data.equipment_id, start_date: data.start_date, end_date: data.end_date }),
  }),
  cancelMyReservation: (id: number) => request(`${API_BASE}/me/reservations/${id}/cancel`, isCustomerReservation, {
    method: 'POST',
  }),
  listMyIncidents: (signal?: AbortSignal) => request(
    `${API_BASE}/me/incidents`, isCustomerIncidentList, { signal: signal ?? null },
  ),
  getMyIncident: (id: number, signal?: AbortSignal) => request(
    `${API_BASE}/me/incidents/${id}`, isCustomerIncident, { signal: signal ?? null },
  ),
  createMyIncident: (reservationId: number, data: CustomerIncidentInput) => request(
    `${API_BASE}/me/reservations/${reservationId}/incidents`, isCustomerIncident, {
      method: 'POST', body: JSON.stringify({ title: data.title, description: data.description }),
    },
  ),
  listEquipment: () => request(`${API_BASE}/equipment`, isEquipmentList),
  getEquipment: (id: number) => request(`${API_BASE}/equipment/${id}`, isEquipment),
  createEquipment: (data: EquipmentInput) => request(`${API_BASE}/equipment`, isEquipment, {
    method: 'POST', body: JSON.stringify(data),
  }),
  updateEquipment: (id: number, data: EquipmentInput) => request(`${API_BASE}/equipment/${id}`, isEquipment, {
    method: 'PUT', body: JSON.stringify(data),
  }),
  patchEquipment: (id: number, data: EquipmentPatch) => request(`${API_BASE}/equipment/${id}`, isEquipment, {
    method: 'PATCH', body: JSON.stringify(data),
  }),
  listReservations: (filters: ReservationFilters = {}) => request(
    `${API_BASE}/reservations${queryString({ ...filters })}`, isReservationList,
  ),
  getReservation: (id: number) => request(`${API_BASE}/reservations/${id}`, isReservation),
  createReservation: (data: ReservationInput) => request(`${API_BASE}/reservations`, isReservation, {
    method: 'POST', body: JSON.stringify({
      equipment_id: data.equipment_id, customer_name: data.customer_name, customer_email: data.customer_email,
      start_date: data.start_date, end_date: data.end_date, external_reference: data.external_reference,
    }),
  }),
  cancelReservation: (id: number) => request(`${API_BASE}/reservations/${id}/cancel`, isReservation, {
    method: 'POST',
  }),
  getEquipmentAvailability: (id: number, range: DateRange) => request(
    `${API_BASE}/equipment/${id}/availability${queryString({ ...range })}`, isAvailability,
  ),
  listIncidents: (filters: IncidentFilters = {}) => request(
    `${API_BASE}/incidents${queryString({ ...filters })}`, isIncidentList,
  ),
  getIncident: (id: number) => request(`${API_BASE}/incidents/${id}`, isIncident),
  createIncident: (data: IncidentInput) => request(`${API_BASE}/incidents`, isIncident, {
    method: 'POST', body: JSON.stringify(data),
  }),
  patchIncident: (id: number, data: IncidentUpdate) => request(`${API_BASE}/incidents/${id}`, isIncident, {
    method: 'PATCH', body: JSON.stringify({
      priority: data.priority, blocking: data.blocking, public_response: data.public_response, internal_notes: data.internal_notes,
    }),
  }),
  changeIncidentStatus: (id: number, data: IncidentStatusChange) => request(`${API_BASE}/incidents/${id}/status`, isIncident, {
    method: 'PATCH', body: JSON.stringify(data),
  }),
  importReservations: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request(`${API_BASE}/imports`, isImportReport, { method: 'POST', body });
  },
};
