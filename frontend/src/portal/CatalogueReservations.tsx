import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { api, type DateRange } from '../api/client';
import { formatDate } from '../lib/dates';

interface ReservationsResult {
  key: string;
  context: string;
  reservations: DateRange[] | null;
  loading: boolean;
  error: string | null;
}

export function CatalogueReservations({ id, name, count, today }: {
  id: number; name: string; count: number; today: string;
}) {
  const panelId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<ReservationsResult>({ key: '', context: '', reservations: null, loading: true, error: null });
  const context = `${id}:${count}:${today}`;
  const key = `${context}:${revision}`;
  const current = result.key === key;
  const loading = !current || result.loading;
  const displayedCount = result.context === context && result.reservations ? result.reservations.length : count;

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let current = true;
    void Promise.resolve().then(async () => {
      if (!current) return;
      setResult((previous) => ({ key, context, reservations: previous.context === context ? previous.reservations : null, loading: true, error: null }));
      const data = await api.getPublicReservationDates(id, controller.signal);
      if (current) setResult({ key, context, reservations: data.reservations, loading: false, error: null });
    }).catch((failure: unknown) => {
      if (current) setResult((previous) => ({ ...previous, key, context, loading: false, error: failure instanceof Error ? failure.message : 'No se pudieron cargar las fechas.' }));
    });
    return () => { current = false; controller.abort(); };
  }, [open, id, context, key]);

  function closeWithEscape(event: KeyboardEvent<HTMLElement>) {
    if (open && event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    }
  }

  return <>
    <button ref={trigger} type="button" className="catalogue-reservation-count" aria-expanded={open} aria-controls={open ? panelId : undefined} aria-label={`${open ? 'Ocultar' : 'Ver'} fechas de ${displayedCount} ${displayedCount === 1 ? 'reserva' : 'reservas'} de ${name}`} onKeyDown={closeWithEscape} onClick={() => {
      if (!open) setRevision((value) => value + 1);
      setOpen(!open);
    }}>
      <strong>{displayedCount} {displayedCount === 1 ? 'reserva' : 'reservas'}</strong>
      <span>En curso y próximas</span>
    </button>
    {open && <section id={panelId} className="catalogue-reservation-dates" aria-label={`Fechas de las reservas de ${name}`} aria-busy={loading} onKeyDown={closeWithEscape}>
      <h4>Fechas de las reservas</h4>
      {loading ? <p role="status">Cargando fechas…</p> : result.error ? <>
        <p role="alert">{result.error}</p>
        <button type="button" className="button button-secondary" onClick={() => { setRevision((value) => value + 1); trigger.current?.focus(); }}>Reintentar fechas</button>
      </> : !result.reservations?.length ? <p role="status">No hay reservas en curso ni próximas.</p> : <>
        <ol aria-label={`Fechas reservadas de ${name}`}>
          {result.reservations.map((reservation, index) => <li key={`${reservation.start_date}:${reservation.end_date}:${index}`}>
            <span>Recogida <time dateTime={reservation.start_date}>{formatDate(reservation.start_date)}</time></span>
            <span>Devolución <time dateTime={reservation.end_date}>{formatDate(reservation.end_date)}</time></span>
          </li>)}
        </ol>
        <p className="catalogue-reservation-note">El día de devolución no se incluye en el alquiler.</p>
      </>}
    </section>}
  </>;
}
