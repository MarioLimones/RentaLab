import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import type { DateRange } from '../api/client';
import { formatDate } from '../lib/dates';
import { completeDateRange, isCalendarDate, todayInMadrid } from './dateRange';
import type { useAvailabilityCalendar } from './useAvailabilityCalendar';
import './availability-calendar.css';

const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

function Chevron({ next = false }: { next?: boolean }) {
  return <svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={next ? 'm8 5 5 5-5 5' : 'm12 5-5 5 5 5'} /></svg>;
}

export function AvailabilityCalendar({ calendar, range, onChange, disabled = false, errors = {}, title = 'Disponibilidad del equipo' }: {
  calendar: ReturnType<typeof useAvailabilityCalendar>;
  range?: DateRange;
  onChange?: (range: DateRange) => void;
  disabled?: boolean;
  errors?: Record<string, string>;
  title?: string;
}) {
  const id = useId();
  const { month, data, loading, error } = calendar;
  const today = todayInMadrid();
  const selectionKey = `${range?.start_date ?? ''}:${range?.end_date ?? ''}`;
  const [selection, setSelection] = useState<{ key: string; field: 'start' | 'end' } | null>(null);
  const selecting = selection?.key === selectionKey ? selection.field : range?.start_date && !range.end_date ? 'end' : 'start';
  const [focusedDate, setFocusedDate] = useState('');
  const [preview, setPreview] = useState<{ date: string; context: string; data: typeof data } | null>(null);
  const pendingFocus = useRef<string | null>(null);
  const table = useRef<HTMLTableElement>(null);
  const interactive = !!range && !!onChange;
  const validRange = !!range && completeDateRange(range);
  const previewContext = `${month}:${selectionKey}:${selecting}`;
  const previewEnd = interactive && !disabled && !loading && !error && selecting === 'end'
    && isCalendarDate(range.start_date) && range.start_date >= today
    && data?.can_book && calendar.canReachMonth && preview?.context === previewContext && preview.data === data
    && preview.date > range.start_date && !data.unavailable_end_dates?.includes(preview.date)
    && !data.occupied_ranges.some((period) => period.start_date < preview.date && period.end_date > range.start_date)
    ? preview.date : null;
  const first = new Date(`${month}-01T12:00:00Z`);
  const label = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(first);
  const offset = (first.getUTCDay() + 6) % 7;
  const last = new Date(first);
  last.setUTCMonth(last.getUTCMonth() + 1, 0);
  const days = last.getUTCDate();
  const weeks = Array.from({ length: Math.ceil((offset + days) / 7) }, (_, week) => Array.from({ length: 7 }, (_, weekday) => {
    const day = week * 7 + weekday - offset + 1;
    return day > 0 && day <= days ? day : null;
  }));
  const tabDate = [focusedDate, range?.start_date, today].find((date) => date?.startsWith(`${month}-`)) ?? `${month}-01`;

  useEffect(() => {
    if (!loading && data && pendingFocus.current) {
      table.current?.querySelector<HTMLButtonElement>(`[data-date="${pendingFocus.current}"]`)?.focus();
      pendingFocus.current = null;
    }
    if (error) pendingFocus.current = null;
  }, [month, loading, data, error]);

  function selectDate(date: string) {
    if (!range || !onChange || disabled) return;
    setPreview(null);
    const next = selecting === 'end' && isCalendarDate(range.start_date) && date > range.start_date
      ? { start_date: range.start_date, end_date: date }
      : { start_date: date, end_date: '' };
    setSelection({ key: `${next.start_date}:${next.end_date}`, field: next.end_date ? 'start' : 'end' });
    setFocusedDate(date);
    onChange(next);
  }

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, date: string) {
    const target = new Date(`${date}T12:00:00Z`);
    const weekday = (target.getUTCDay() + 6) % 7;
    const shifts: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -weekday, End: 6 - weekday };
    if (event.key in shifts) target.setUTCDate(target.getUTCDate() + shifts[event.key]!);
    else if (event.key === 'PageUp' || event.key === 'PageDown') {
      const day = target.getUTCDate();
      target.setUTCDate(1);
      target.setUTCMonth(target.getUTCMonth() + (event.key === 'PageUp' ? -1 : 1));
      const monthEnd = new Date(target);
      monthEnd.setUTCMonth(monthEnd.getUTCMonth() + 1, 0);
      target.setUTCDate(Math.min(day, monthEnd.getUTCDate()));
    } else return;
    event.preventDefault();
    if (target.getUTCFullYear() < 1 || target.getUTCFullYear() > 9999) return;
    const next = target.toISOString().slice(0, 10);
    if (next > '9999-11-30') return;
    setFocusedDate(next);
    previewDate(next, true);
    if (next.slice(0, 7) !== month) {
      pendingFocus.current = next;
      calendar.goTo(next.slice(0, 7));
    } else table.current?.querySelector<HTMLButtonElement>(`[data-date="${next}"]`)?.focus();
  }

  function editDate(field: 'start' | 'end') {
    setPreview(null);
    setSelection({ key: selectionKey, field: field === 'end' && !isCalendarDate(range?.start_date ?? '') ? 'start' : field });
    const date = field === 'start' ? range?.start_date : range?.end_date || range?.start_date;
    if (date) calendar.goTo(date.slice(0, 7));
  }

  function previewDate(date: string, allowed: boolean) {
    setPreview(allowed && !disabled && selecting === 'end' && range && date > range.start_date
      ? { date, context: previewContext, data } : null);
  }

  return <section className="availability-calendar" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`} className="availability-calendar-heading"><svg aria-hidden="true" viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4m8-4v4M3 8h14m-9 4h4" /></svg>{title}</h3>
    {interactive && <>
      <div className="calendar-date-summary" role="group" aria-label="Fechas del alquiler">
        <div className="calendar-date-field"><button type="button" id="start_date" className={selecting === 'start' ? 'is-editing' : ''} disabled={disabled} aria-pressed={selecting === 'start'} aria-invalid={!!errors.start_date} aria-describedby={errors.start_date ? `${id}-start-error` : undefined} aria-label={`Fecha de inicio: ${range.start_date ? formatDate(range.start_date) : 'Elegir día'}`} onClick={() => editDate('start')}><span>Recogida</span><strong>{range.start_date ? formatDate(range.start_date) : 'Elegir día'}</strong></button>{errors.start_date && <p className="field-error" id={`${id}-start-error`}>{errors.start_date}</p>}</div>
        <span className="calendar-date-arrow" aria-hidden="true">→</span>
        <div className="calendar-date-field"><button type="button" id="end_date" className={selecting === 'end' ? 'is-editing' : ''} disabled={disabled} aria-pressed={selecting === 'end'} aria-invalid={!!errors.end_date} aria-describedby={errors.end_date ? `${id}-end-error` : undefined} aria-label={`Fecha de devolución: ${range.end_date ? formatDate(range.end_date) : 'Elegir día'}`} onClick={() => editDate('end')}><span>Devolución</span><strong>{range.end_date ? formatDate(range.end_date) : 'Elegir día'}</strong></button>{errors.end_date && <p className="field-error" id={`${id}-end-error`}>{errors.end_date}</p>}</div>
      </div>
      <div className="calendar-selection-hint"><p aria-live="polite">{selecting === 'end' ? '2. Elige el día de devolución' : validRange ? 'Tus fechas están seleccionadas' : '1. Elige el día de recogida'}</p>{(range.start_date || range.end_date) && <button type="button" disabled={disabled} onClick={() => { calendar.goTo(month); setSelection(null); onChange({ start_date: '', end_date: '' }); }}>Cambiar fechas</button>}</div>
    </>}
    <div className="availability-calendar-navigation">
      <p aria-live="polite">{label}</p>
      <div><button type="button" aria-label="Mes anterior" onClick={calendar.previous} disabled={disabled || month <= '0001-01'}><Chevron /></button><button type="button" aria-label="Mes siguiente" onClick={calendar.next} disabled={disabled || month >= '9999-11'}><Chevron next /></button></div>
    </div>
    {loading && !data ? <div className="calendar-loading" role="status"><span className="calendar-loading-mark" aria-hidden="true" />Cargando disponibilidad…</div> : error ? <div className="calendar-load-error"><p role="alert">No se pudo actualizar el calendario. {error}</p><button type="button" className="button button-secondary" onClick={calendar.retry}>Reintentar calendario</button></div> : data && <>
      {loading && <p role="status" className="availability-calendar-help">Actualizando disponibilidad…</p>}
      {!data.can_book && <p className="availability-calendar-blocked">Este equipo no admite nuevas reservas en este momento. Consulta otro equipo o vuelve más adelante.</p>}
      <table ref={table} className="availability-calendar-table" aria-busy={loading || undefined} onPointerLeave={() => setPreview(null)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setPreview(null); }} aria-describedby={`${id}-legend ${id}-help${interactive ? ` ${id}-keyboard` : ''}`}>
        <caption className="sr-only">Ocupación de {label}</caption>
        <thead><tr>{weekdays.map((day) => <th scope="col" key={day}><abbr title={day}>{day.slice(0, 2)}</abbr></th>)}</tr></thead>
        <tbody>{weeks.map((week, index) => <tr key={index}>{week.map((day, weekday) => {
          if (!day) return <td key={weekday} />;
          const date = `${month}-${String(day).padStart(2, '0')}`;
          const occupied = data.occupied_ranges.some((period) => period.start_date <= date && date < period.end_date);
          const past = date < today;
          const ending = selecting === 'end' && !!range?.start_date && date > range.start_date;
          const unavailableEnd = ending && data.unavailable_end_dates?.includes(date);
          const crossesOccupied = ending && (!calendar.canReachMonth || unavailableEnd || data.occupied_ranges.some((period) => period.start_date < date && period.end_date > range.start_date));
          const returnPossible = ending && occupied && !crossesOccupied && data.can_book && !past;
          const unavailable = loading || !data.can_book || past || (occupied && !returnPossible) || crossesOccupied;
          const start = range?.start_date === date;
          const end = range?.end_date === date;
          const inRange = validRange && date > range.start_date && date < range.end_date;
          const inPreview = !!previewEnd && !!range && date > range.start_date && date < previewEnd;
          const previewEndpoint = date === previewEnd;
          const status = occupied ? 'Ocupado' : !data.can_book ? 'No admite reservas' : past ? 'Fecha pasada' : unavailableEnd ? 'No disponible para esta devolución' : 'Disponible';
          const accessibleName = `${formatDate(date)}: ${status}`;
          const classes = ['calendar-day', occupied ? 'calendar-day-occupied' : !data.can_book || unavailableEnd ? 'calendar-day-blocked' : past ? 'calendar-day-past' : 'calendar-day-available', returnPossible ? 'calendar-day-return' : '', start ? 'calendar-day-start' : '', end ? 'calendar-day-end' : '', inRange ? 'calendar-day-in-range' : '', inPreview ? 'calendar-day-preview' : '', previewEndpoint ? 'calendar-day-preview-end' : ''].filter(Boolean).join(' ');
          return <td key={weekday} className={classes} aria-label={accessibleName}>
            {interactive ? <button type="button" data-date={date} tabIndex={date === tabDate ? 0 : -1} aria-label={`${accessibleName}${returnPossible ? '. Devolución posible' : unavailableEnd ? '. El periodo no está disponible desde la recogida seleccionada' : crossesOccupied ? '. El periodo cruza días ocupados' : ''}${start ? '. Recogida seleccionada' : end ? '. Devolución seleccionada' : ''}`} aria-current={date === today ? 'date' : undefined} aria-pressed={start || end || inRange} aria-disabled={unavailable || undefined} disabled={disabled} onPointerEnter={(event) => { if (event.pointerType === 'mouse' || event.pointerType === 'pen') previewDate(date, !unavailable); }} onFocus={(event) => { setFocusedDate(date); if (event.currentTarget.matches(':focus-visible')) previewDate(date, !unavailable); }} onClick={() => { if (!unavailable) selectDate(date); }} onKeyDown={(event) => moveFocus(event, date)}><time dateTime={date}>{day}</time><span className="calendar-day-indicator" aria-hidden="true" /></button> : <time dateTime={date}>{day}</time>}
          </td>;
        })}</tr>)}</tbody>
      </table>
      <div className="availability-calendar-legend" id={`${id}-legend`}><span><span className={`calendar-legend-swatch ${data.can_book ? 'calendar-swatch-available' : 'calendar-swatch-blocked'}`} aria-hidden="true" />{data.can_book ? 'Disponible' : 'No admite reservas'}</span><span><span className="calendar-legend-swatch calendar-swatch-occupied" aria-hidden="true" />Ocupado</span>{interactive && <span><span className="calendar-legend-swatch calendar-swatch-selected" aria-hidden="true" />Tus fechas</span>}</div>
    </>}
    <p className="availability-calendar-help" id={`${id}-help`}>La devolución no cuenta como día de alquiler.{interactive && selecting === 'end' && !!data?.unavailable_end_dates?.length && ' Los días desactivados no permiten reservar todo el periodo desde la recogida.'}</p>
    {interactive && <p id={`${id}-keyboard`} className="sr-only">Usa las flechas para recorrer los días, Inicio y Fin para la semana, y Re Pág o Av Pág para cambiar de mes. Pulsa Intro para elegir una fecha.</p>}
  </section>;
}
