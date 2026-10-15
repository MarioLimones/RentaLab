import type { DateRange } from '../api/client';

export function todayInMadrid(): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const part = (name: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === name)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= (days[month - 1] ?? 0);
}

/** Form validation only: the API remains the authority for rental rules. */
export function dateRangeErrors(range: DateRange, required = false): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!range.start_date && !range.end_date && !required) return errors;
  if (!isCalendarDate(range.start_date)) errors.start_date = 'Selecciona una fecha de inicio válida.';
  if (!isCalendarDate(range.end_date)) errors.end_date = 'Selecciona una fecha de fin válida.';
  if (Object.keys(errors).length === 0 && range.end_date <= range.start_date) errors.end_date = 'La fecha de fin debe ser posterior al inicio.';
  return errors;
}

export function completeDateRange(range: DateRange): boolean {
  return !!range.start_date && !!range.end_date && Object.keys(dateRangeErrors(range, true)).length === 0;
}

export function rangeSearch(range: DateRange): string {
  const search = new URLSearchParams();
  if (range.start_date) search.set('start_date', range.start_date);
  if (range.end_date) search.set('end_date', range.end_date);
  return search.size ? `?${search.toString()}` : '';
}
