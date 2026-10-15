import type { IntervaloFechas } from '../api/cliente';

export function hoyEnMadrid(): string {
  const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const parte = (nombre: Intl.DateTimeFormatPartTypes) => partes.find((elementoLista) => elementoLista.type === nombre)?.value ?? '';
  return `${parte('year')}-${parte('month')}-${parte('day')}`;
}

export function esFechaCalendario(valor: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return false;
  const ano = Number(valor.slice(0, 4));
  const mes = Number(valor.slice(5, 7));
  const dia = Number(valor.slice(8, 10));
  const bisiesto = ano % 4 === 0 && (ano % 100 !== 0 || ano % 400 === 0);
  const dias = [31, bisiesto ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return ano > 0 && mes >= 1 && mes <= 12 && dia >= 1 && dia <= (dias[mes - 1] ?? 0);
}

/** Validación del formulario: la API sigue siendo la autoridad para las reglas de alquiler. */
export function erroresIntervaloFechas(intervalo: IntervaloFechas, obligatorio = false): Record<string, string> {
  const errores: Record<string, string> = {};
  if (!intervalo.start_date && !intervalo.end_date && !obligatorio) return errores;
  if (!esFechaCalendario(intervalo.start_date)) errores.start_date = 'Selecciona una fecha de inicio válida.';
  if (!esFechaCalendario(intervalo.end_date)) errores.end_date = 'Selecciona una fecha de fin válida.';
  if (Object.keys(errores).length === 0 && intervalo.end_date <= intervalo.start_date) errores.end_date = 'La fecha de fin debe ser posterior al inicio.';
  return errores;
}

export function completarIntervaloFechas(intervalo: IntervaloFechas): boolean {
  return !!intervalo.start_date && !!intervalo.end_date && Object.keys(erroresIntervaloFechas(intervalo, true)).length === 0;
}

export function busquedaIntervalo(intervalo: IntervaloFechas): string {
  const busqueda = new URLSearchParams();
  if (intervalo.start_date) busqueda.set('start_date', intervalo.start_date);
  if (intervalo.end_date) busqueda.set('end_date', intervalo.end_date);
  return busqueda.size ? `?${busqueda.toString()}` : '';
}
