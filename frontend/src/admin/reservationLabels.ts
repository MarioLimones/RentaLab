import type { Reservation } from '../types/api';

export const reservationOrigins = {
  portal: 'Portal de cliente',
  admin: 'Administración',
  csv: 'Importación CSV',
  legacy: 'Histórico · origen no conocido',
} as const;

export function reservationOwner(reservation: Reservation): string {
  return reservation.customer_user_id ? `Cuenta cliente #${reservation.customer_user_id}` : 'Sin propietario de cuenta';
}

export function reservationOrigin(reservation: Reservation): string {
  return reservationOrigins[reservation.origin ?? 'legacy'];
}
