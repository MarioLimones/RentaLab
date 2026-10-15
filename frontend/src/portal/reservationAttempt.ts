import type { CustomerReservationInput, DateRange } from '../types/api';
import { completeDateRange } from './dateRange';

const STORAGE_KEY = 'rentalab.reservation-attempts.v1';
const MAX_ATTEMPTS = 20;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export interface ReservationAttempt {
  scope: string;
  key: string;
  phase: 'ready' | 'uncertain' | 'complete';
  reservationIds: number[];
}
let memory: ReservationAttempt[] = [];

export function reservationScope(userId: number | null, input: CustomerReservationInput): string | null {
  return userId !== null && completeDateRange(input) ? `${userId}:${input.equipment_id}:${input.start_date}:${input.end_date}` : null;
}

export function batchReservationScope(userId: number | null, equipmentIds: number[], range: DateRange): string | null {
  return userId !== null && equipmentIds.length > 0 && completeDateRange(range)
    ? `${userId}:batch:${equipmentIds.join(',')}:${range.start_date}:${range.end_date}` : null;
}

function isAttempt(value: unknown): value is ReservationAttempt {
  return typeof value === 'object' && value !== null && 'scope' in value && 'key' in value && 'phase' in value && 'reservationIds' in value
    && typeof value.scope === 'string' && /^[1-9]\d*:(?:[1-9]\d*|batch:[1-9]\d*(?:,[1-9]\d*)*):\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/.test(value.scope)
    && typeof value.key === 'string' && uuid.test(value.key)
    && (value.phase === 'ready' || value.phase === 'uncertain' || value.phase === 'complete')
    && Array.isArray(value.reservationIds) && value.reservationIds.length <= 50
    && value.reservationIds.every((id) => typeof id === 'number' && Number.isSafeInteger(id) && id > 0)
    && (value.phase !== 'complete' || value.reservationIds.length > 0);
}

function attempts(): ReservationAttempt[] {
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '[]');
    memory = Array.isArray(stored) ? stored.filter(isAttempt).slice(-MAX_ATTEMPTS) : [];
  } catch { /* In-memory recovery still protects a retry when storage is unavailable. */ }
  return memory;
}

function persist(next: ReservationAttempt[]) {
  memory = next.slice(-MAX_ATTEMPTS);
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(memory)); } catch { /* No credentials or customer contact data are stored. */ }
}

export function readReservationAttempt(scope: string | null): ReservationAttempt | null {
  return scope ? attempts().find((attempt) => attempt.scope === scope) ?? null : null;
}

/** Restore a pending/completed batch's exact selection before a list reload defaults to all. */
export function readBatchReservationSelection(userId: number, range: DateRange, availableIds: number[]): number[] | null {
  for (const attempt of [...attempts()].reverse()) {
    const [owner, kind, ids, start, end] = attempt.scope.split(':');
    if (owner !== String(userId) || kind !== 'batch' || start !== range.start_date || end !== range.end_date || !ids) continue;
    const selection = ids.split(',').map(Number);
    if (attempt.phase !== 'ready' || selection.every((id) => availableIds.includes(id))) return selection;
  }
  return null;
}

export function saveReservationAttempt(attempt: ReservationAttempt) {
  persist([...attempts().filter((item) => item.scope !== attempt.scope), attempt]);
}

export function forgetReservationAttempt(scope: string | null) {
  if (scope) persist(attempts().filter((attempt) => attempt.scope !== scope));
}

export function newReservationAttempt(scope: string): ReservationAttempt {
  return { scope, key: crypto.randomUUID(), phase: 'ready', reservationIds: [] };
}
