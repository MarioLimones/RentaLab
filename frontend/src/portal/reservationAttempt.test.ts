import { beforeEach, describe, expect, it } from 'vitest';
import { batchReservationScope, forgetReservationAttempt, newReservationAttempt, readReservationAttempt, reservationScope, saveReservationAttempt } from './reservationAttempt';

const range = { start_date: '2027-11-10', end_date: '2027-11-12' };
beforeEach(() => { sessionStorage.clear(); });

describe('reservation intent persistence', () => {
  it('isolates account, product, dates and batch operation while retaining an uncertain UUID', () => {
    const scope = reservationScope(4, { equipment_id: 1, ...range })!;
    const attempt = { ...newReservationAttempt(scope), phase: 'uncertain' as const };
    saveReservationAttempt(attempt);
    expect(readReservationAttempt(scope)).toEqual(attempt);
    expect(readReservationAttempt(reservationScope(5, { equipment_id: 1, ...range }))).toBeNull();
    expect(readReservationAttempt(reservationScope(4, { equipment_id: 2, ...range }))).toBeNull();
    expect(readReservationAttempt(batchReservationScope(4, [1], range))).toBeNull();
    forgetReservationAttempt(scope);
    expect(readReservationAttempt(scope)).toBeNull();
    expect(newReservationAttempt(scope).key).not.toBe(attempt.key);
  });

  it('bounds stored metadata and rejects malformed session storage', () => {
    for (let id = 1; id <= 30; id++) saveReservationAttempt(newReservationAttempt(reservationScope(4, { equipment_id: id, ...range })!));
    const entries: unknown[] = JSON.parse(sessionStorage.getItem('rentalab.reservation-attempts.v1')!);
    expect(entries).toHaveLength(20);
    expect(JSON.stringify(entries)).not.toMatch(/password|token|email|name/);
    sessionStorage.setItem('rentalab.reservation-attempts.v1', JSON.stringify([{ scope: reservationScope(4, { equipment_id: 1, ...range }), key: 'invalid', phase: 'complete', reservationIds: ['31'] }]));
    expect(readReservationAttempt(reservationScope(4, { equipment_id: 1, ...range }))).toBeNull();
  });
});
