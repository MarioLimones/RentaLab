import { beforeEach, describe, expect, it } from 'vitest';
import { ambitoReservaConjunta, olvidarIntentoReserva, nuevoIntentoReserva, leerIntentoReserva, ambitoReserva, guardarIntentoReserva } from './intentoReserva';

const intervalo = { start_date: '2027-11-10', end_date: '2027-11-12' };
beforeEach(() => { sessionStorage.clear(); });

describe("persistencia de la intención de reserva", () => {
  it("aísla cuenta, producto, fechas y operación conjunta conservando un UUID incierto", () => {
    const ambito = ambitoReserva(4, { equipment_id: 1, ...intervalo })!;
    const intento = { ...nuevoIntentoReserva(ambito), phase: 'uncertain' as const };
    guardarIntentoReserva(intento);
    expect(leerIntentoReserva(ambito)).toEqual(intento);
    expect(leerIntentoReserva(ambitoReserva(5, { equipment_id: 1, ...intervalo }))).toBeNull();
    expect(leerIntentoReserva(ambitoReserva(4, { equipment_id: 2, ...intervalo }))).toBeNull();
    expect(leerIntentoReserva(ambitoReservaConjunta(4, [1], intervalo))).toBeNull();
    olvidarIntentoReserva(ambito);
    expect(leerIntentoReserva(ambito)).toBeNull();
    expect(nuevoIntentoReserva(ambito).key).not.toBe(intento.key);
  });

  it("limita los metadatos guardados y rechaza datos mal formados del almacenamiento de sesión", () => {
    for (let id = 1; id <= 30; id++) guardarIntentoReserva(nuevoIntentoReserva(ambitoReserva(4, { equipment_id: id, ...intervalo })!));
    const entradas: unknown[] = JSON.parse(sessionStorage.getItem('rentalab.reservation-attempts.v1')!);
    expect(entradas).toHaveLength(20);
    expect(JSON.stringify(entradas)).not.toMatch(/password|token|email|name/);
    sessionStorage.setItem('rentalab.reservation-attempts.v1', JSON.stringify([{ scope: ambitoReserva(4, { equipment_id: 1, ...intervalo }), key: 'invalid', phase: 'complete', reservationIds: ['31'] }]));
    expect(leerIntentoReserva(ambitoReserva(4, { equipment_id: 1, ...intervalo }))).toBeNull();
  });
});
