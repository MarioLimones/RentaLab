import type { EntradaReservaCliente, IntervaloFechas } from '../tipos/api';
import { completarIntervaloFechas } from './intervaloFechas';

const CLAVE_ALMACENAMIENTO = 'rentalab.reservation-attempts.v1';
const MAXIMO_INTENTOS = 20;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export interface IntentoReserva {
  scope: string;
  key: string;
  phase: 'ready' | 'uncertain' | 'complete';
  reservationIds: number[];
}
let memoria: IntentoReserva[] = [];

export function ambitoReserva(idUsuario: number | null, entrada: EntradaReservaCliente): string | null {
  return idUsuario !== null && completarIntervaloFechas(entrada) ? `${idUsuario}:${entrada.equipment_id}:${entrada.start_date}:${entrada.end_date}` : null;
}

export function ambitoReservaConjunta(idUsuario: number | null, idsEquipos: number[], intervalo: IntervaloFechas): string | null {
  return idUsuario !== null && idsEquipos.length > 0 && completarIntervaloFechas(intervalo)
    ? `${idUsuario}:batch:${idsEquipos.join(',')}:${intervalo.start_date}:${intervalo.end_date}` : null;
}

function esIntento(valor: unknown): valor is IntentoReserva {
  return typeof valor === 'object' && valor !== null && 'scope' in valor && 'key' in valor && 'phase' in valor && 'reservationIds' in valor
    && typeof valor.scope === 'string' && /^[1-9]\d*:(?:[1-9]\d*|batch:[1-9]\d*(?:,[1-9]\d*)*):\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/.test(valor.scope)
    && typeof valor.key === 'string' && uuid.test(valor.key)
    && (valor.phase === 'ready' || valor.phase === 'uncertain' || valor.phase === 'complete')
    && Array.isArray(valor.reservationIds) && valor.reservationIds.length <= 50
    && valor.reservationIds.every((id) => typeof id === 'number' && Number.isSafeInteger(id) && id > 0)
    && (valor.phase !== 'complete' || valor.reservationIds.length > 0);
}

function intentos(): IntentoReserva[] {
  try {
    const almacenado: unknown = JSON.parse(sessionStorage.getItem(CLAVE_ALMACENAMIENTO) ?? '[]');
    memoria = Array.isArray(almacenado) ? almacenado.filter(esIntento).slice(-MAXIMO_INTENTOS) : [];
  } catch { /* La recuperación en memoria sigue protegiendo los reintentos cuando el almacenamiento no está disponible. */ }
  return memoria;
}

function conservar(siguiente: IntentoReserva[]) {
  memoria = siguiente.slice(-MAXIMO_INTENTOS);
  try { sessionStorage.setItem(CLAVE_ALMACENAMIENTO, JSON.stringify(memoria)); } catch { /* No se guardan credenciales ni datos de contacto del cliente. */ }
}

export function leerIntentoReserva(ambito: string | null): IntentoReserva | null {
  return ambito ? intentos().find((intento) => intento.scope === ambito) ?? null : null;
}

/** Restaura la selección exacta de una reserva conjunta pendiente o completada antes de que la recarga seleccione todo. */
export function leerSeleccionReservasConjuntas(idUsuario: number, intervalo: IntervaloFechas, idsDisponibles: number[]): number[] | null {
  for (const intento of [...intentos()].reverse()) {
    const [titular, clase, ids, inicio, fin] = intento.scope.split(':');
    if (titular !== String(idUsuario) || clase !== 'batch' || inicio !== intervalo.start_date || fin !== intervalo.end_date || !ids) continue;
    const seleccion = ids.split(',').map(Number);
    if (intento.phase !== 'ready' || seleccion.every((id) => idsDisponibles.includes(id))) return seleccion;
  }
  return null;
}

export function guardarIntentoReserva(intento: IntentoReserva) {
  conservar([...intentos().filter((elementoLista) => elementoLista.scope !== intento.scope), intento]);
}

export function olvidarIntentoReserva(ambito: string | null) {
  if (ambito) conservar(intentos().filter((intento) => intento.scope !== ambito));
}

export function nuevoIntentoReserva(ambito: string): IntentoReserva {
  return { scope: ambito, key: crypto.randomUUID(), phase: 'ready', reservationIds: [] };
}
