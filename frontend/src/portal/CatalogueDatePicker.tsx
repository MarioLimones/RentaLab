import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import type { DateRange } from '../api/client';
import { formatDate } from '../lib/dates';
import { completeDateRange, isCalendarDate, todayInMadrid } from './dateRange';
import './catalogue-date-picker.css';

type DateField = keyof DateRange;
interface CalendarView { field: DateField; month: string; focused: string; }
const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

function CalendarIcon() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4m8-4v4M3 8h14m-9 4h4" /></svg>;
}

export function CatalogueDatePicker({ value, onChange, errors = {}, disabled = false }: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
}) {
  const id = useId();
  const root = useRef<HTMLFieldSetElement>(null);
  const table = useRef<HTMLTableElement>(null);
  const startTrigger = useRef<HTMLButtonElement>(null);
  const endTrigger = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLButtonElement | null>(null);
  const pendingFocus = useRef<string | null>(null);
  const [view, setView] = useState<CalendarView | null>(null);
  const [preview, setPreview] = useState<{ date: string; context: string } | null>(null);
  const open = !!view && !disabled;
  const today = todayInMadrid();
  const month = view?.month ?? today.slice(0, 7);
  const first = new Date(`${month}-01T12:00:00Z`);
  const last = new Date(first);
  last.setUTCMonth(last.getUTCMonth() + 1, 0);
  const label = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(first);
  const offset = (first.getUTCDay() + 6) % 7;
  const weeks = Array.from({ length: Math.ceil((offset + last.getUTCDate()) / 7) }, (_, week) => Array.from({ length: 7 }, (_, weekday) => {
    const day = week * 7 + weekday - offset + 1;
    return day > 0 && day <= last.getUTCDate() ? day : null;
  }));
  const validRange = completeDateRange(value);
  const previewContext = `${month}:${view?.field}:${value.start_date}:${value.end_date}`;
  const previewEnd = open && view.field === 'end_date' && isCalendarDate(value.start_date)
    && preview?.context === previewContext && preview.date > value.start_date ? preview.date : null;

  function previewDate(date: string, targetMonth = month) {
    setPreview(view?.field === 'end_date' && isCalendarDate(value.start_date) && date > value.start_date
      ? { date, context: `${targetMonth}:${view.field}:${value.start_date}:${value.end_date}` } : null);
  }

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setView(null);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  useEffect(() => {
    if (open && pendingFocus.current) {
      table.current?.querySelector<HTMLButtonElement>(`[data-date="${pendingFocus.current}"]`)?.focus();
      pendingFocus.current = null;
    }
  }, [open, month, view?.focused]);

  function show(field: DateField) {
    setPreview(null);
    const trigger = field === 'start_date' ? startTrigger.current : endTrigger.current;
    if (open && view.field === field) { setView(null); return; }
    const selected = [value[field], value.start_date, today].find(isCalendarDate) ?? today;
    returnFocus.current = trigger;
    pendingFocus.current = selected;
    setView({ field: field === 'end_date' && !isCalendarDate(value.start_date) ? 'start_date' : field, month: selected.slice(0, 7), focused: selected });
  }

  function close() {
    setPreview(null);
    setView(null);
    returnFocus.current?.focus();
  }

  function choose(date: string) {
    if (!view || disabled) return;
    setPreview(null);
    if (view.field === 'end_date' && isCalendarDate(value.start_date) && date > value.start_date) {
      onChange({ start_date: value.start_date, end_date: date });
      setView(null);
      endTrigger.current?.focus();
    } else {
      onChange({ start_date: date, end_date: '' });
      setView({ ...view, field: 'end_date', focused: date });
    }
  }

  function changeMonth(amount: number) {
    if (!view) return;
    setPreview(null);
    const target = new Date(`${view.month}-01T12:00:00Z`);
    target.setUTCMonth(target.getUTCMonth() + amount);
    if (target.getUTCFullYear() < 1 || target.getUTCFullYear() > 9999) return;
    const date = target.toISOString().slice(0, 10);
    setView({ ...view, month: date.slice(0, 7), focused: date });
  }

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, date: string) {
    if (!view) return;
    const target = new Date(`${date}T12:00:00Z`);
    const weekday = (target.getUTCDay() + 6) % 7;
    const shifts: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -weekday, End: 6 - weekday };
    if (event.key in shifts) target.setUTCDate(target.getUTCDate() + shifts[event.key]!);
    else if (event.key === 'PageUp' || event.key === 'PageDown') {
      const day = target.getUTCDate();
      target.setUTCDate(1);
      target.setUTCMonth(target.getUTCMonth() + (event.key === 'PageUp' ? -1 : 1));
      const end = new Date(target);
      end.setUTCMonth(end.getUTCMonth() + 1, 0);
      target.setUTCDate(Math.min(day, end.getUTCDate()));
    } else return;
    event.preventDefault();
    if (target.getUTCFullYear() < 1 || target.getUTCFullYear() > 9999) return;
    const next = target.toISOString().slice(0, 10);
    previewDate(next, next.slice(0, 7));
    pendingFocus.current = next;
    setView({ ...view, month: next.slice(0, 7), focused: next });
  }

  return <fieldset ref={root} className="catalogue-date-picker" disabled={disabled} onKeyDown={(event) => { if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); } }} onBlur={(event) => {
    if (open && event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setView(null);
  }}>
    <legend className="sr-only">Fechas del alquiler</legend>
    {(['start_date', 'end_date'] as const).map((field) => <div className="field catalogue-date-field" key={field}>
      <label htmlFor={field}>{field === 'start_date' ? 'Fecha de inicio' : 'Fecha de fin'}</label>
      <button ref={field === 'start_date' ? startTrigger : endTrigger} id={field} type="button" className={`catalogue-date-trigger${open && view.field === field ? ' is-open' : ''}`} aria-label={`${field === 'start_date' ? 'Fecha de inicio' : 'Fecha de fin'}: ${value[field] ? formatDate(value[field]) : 'Elegir fecha'}`} aria-haspopup="dialog" aria-expanded={open && view.field === field} aria-controls={open ? `${id}-calendar` : undefined} aria-invalid={!!errors[field]} aria-describedby={[field === 'end_date' ? `${id}-return-help` : '', errors[field] ? `${id}-${field}-error` : ''].filter(Boolean).join(' ') || undefined} onClick={() => show(field)}><span className={value[field] ? '' : 'catalogue-date-placeholder'}>{value[field] ? formatDate(value[field]) : 'Elegir fecha'}</span><CalendarIcon /></button>
      {field === 'end_date' && <p className="field-hint" id={`${id}-return-help`}>Día de devolución, no incluido en el alquiler.</p>}
      {errors[field] && <p className="field-error" id={`${id}-${field}-error`}>{errors[field]}</p>}
    </div>)}
    {open && <div id={`${id}-calendar`} className="catalogue-date-popover" role="dialog" aria-label="Fechas del alquiler">
      <div className="catalogue-date-popover-heading"><div><p>Fechas del alquiler</p><span aria-live="polite">{view.field === 'start_date' ? 'Elige el día de recogida' : 'Elige el día de devolución'}</span></div><button className="catalogue-date-icon-button" type="button" aria-label="Cerrar calendario" onClick={close}><svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="m5 5 10 10M15 5 5 15" /></svg></button></div>
      <div className="catalogue-date-navigation"><p aria-live="polite">{label}</p><div>{[-1, 1].map((amount) => <button key={amount} type="button" className="catalogue-date-icon-button" aria-label={amount === -1 ? 'Mes anterior' : 'Mes siguiente'} disabled={amount === -1 ? month <= '0001-01' : month >= '9999-12'} onClick={() => changeMonth(amount)}><svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={amount === -1 ? 'm12 5-5 5 5 5' : 'm8 5 5 5-5 5'} /></svg></button>)}</div></div>
      <table ref={table} className="catalogue-date-table" onPointerLeave={() => setPreview(null)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setPreview(null); }} aria-describedby={`${id}-calendar-help`}>
        <caption className="sr-only">{label}</caption>
        <thead><tr>{weekdays.map((day) => <th scope="col" key={day}><abbr title={day}>{day.slice(0, 2)}</abbr></th>)}</tr></thead>
        <tbody>{weeks.map((week, index) => <tr key={index}>{week.map((day, weekday) => {
          if (!day) return <td key={weekday} />;
          const date = `${month}-${String(day).padStart(2, '0')}`;
          const start = value.start_date === date;
          const end = value.end_date === date;
          const between = validRange && date > value.start_date && date < value.end_date;
          const inPreview = !!previewEnd && date > value.start_date && date < previewEnd;
          return <td key={weekday} className={[start || end ? 'is-endpoint' : between ? 'is-in-range' : '', date < today ? 'is-past' : '', inPreview ? 'is-preview' : '', date === previewEnd ? 'is-preview-end' : ''].filter(Boolean).join(' ')}><button type="button" data-date={date} tabIndex={date === view.focused ? 0 : -1} aria-label={formatDate(date)} aria-current={date === today ? 'date' : undefined} aria-pressed={start || end || between} onPointerEnter={(event) => { if (event.pointerType === 'mouse' || event.pointerType === 'pen') previewDate(date); }} onFocus={(event) => { setView((previous) => previous && previous.focused !== date ? { ...previous, focused: date } : previous); if (event.currentTarget.matches(':focus-visible')) previewDate(date); }} onKeyDown={(event) => moveFocus(event, date)} onClick={() => choose(date)}><time dateTime={date}>{day}</time></button></td>;
        })}</tr>)}</tbody>
      </table>
      <p className="catalogue-date-calendar-help" id={`${id}-calendar-help`}>La devolución no cuenta como día de alquiler.<span className="sr-only"> Usa las flechas para recorrer los días, Inicio y Fin para la semana, Re Pág o Av Pág para cambiar de mes e Intro para elegir.</span></p>
      <div className="catalogue-date-footer"><button type="button" onClick={() => { pendingFocus.current = today; setView({ ...view, month: today.slice(0, 7), focused: today }); }}>Hoy</button><button type="button" disabled={!value.start_date && !value.end_date} onClick={() => { onChange({ start_date: '', end_date: '' }); setView(null); startTrigger.current?.focus(); }}>Borrar fechas</button></div>
    </div>}
  </fieldset>;
}
