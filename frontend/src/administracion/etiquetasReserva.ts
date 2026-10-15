import type { Reserva } from '../tipos/api';

export const origenesReserva = {
  portal: 'Portal de cliente',
  admin: 'Administración',
  csv: 'Importación CSV',
  legacy: 'Histórico · origen no conocido',
} as const;

export function titularReserva(reserva: Reserva): string {
  return reserva.customer_user_id ? `Cuenta cliente #${reserva.customer_user_id}` : 'Sin propietario de cuenta';
}

export function origenReserva(reserva: Reserva): string {
  return origenesReserva[reserva.origin ?? 'legacy'];
}
