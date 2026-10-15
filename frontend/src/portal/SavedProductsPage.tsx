import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError, type CustomerReservation, type DateRange, type PublicAvailability, type PublicEquipment } from '../api/client';
import { useAuth } from '../auth/context';
import { EmptyState, Notice, PageHeader } from '../components/ui';
import { formatDate } from '../lib/dates';
import { AvailabilityCalendar } from './AvailabilityCalendar';
import { completeDateRange, dateRangeErrors, rangeSearch, todayInMadrid } from './dateRange';
import { ProductImage } from './ProductImage';
import { useSavedProducts } from './savedProductsContext';
import { useAvailabilityCalendar } from './useAvailabilityCalendar';
import { useSharedAvailabilityCalendar } from './useSharedAvailabilityCalendar';
import { batchReservationScope, newReservationAttempt, readBatchReservationSelection, readReservationAttempt, saveReservationAttempt, type ReservationAttempt } from './reservationAttempt';
import './catalogue.css';
import './saved-products.css';

interface ProductResult { equipment: PublicEquipment | null; error: string | null; }

function ProductCalendar({ id, selectedDate, revision }: { id: number; selectedDate: string; revision: number }) {
  const calendar = useAvailabilityCalendar(id, selectedDate, revision);
  return <AvailabilityCalendar calendar={calendar} />;
}

export default function SavedProductsPage() {
  const saved = useSavedProducts();
  const { session } = useAuth();
  const customerId = session?.role === 'customer' ? session.user?.id ?? null : null;
  const [search, setSearch] = useSearchParams();
  const [excluded, setExcluded] = useState<number[]>([]);
  const [recoveryIds, setRecoveryIds] = useState<number[] | null>(null);
  const [selectionAccount, setSelectionAccount] = useState(customerId);
  const [selectionRestored, setSelectionRestored] = useState(false);
  const [revision, setRevision] = useState(0);
  const [products, setProducts] = useState({ key: '', items: {} as Record<number, ProductResult>, loading: true });
  const [availability, setAvailability] = useState({ key: '', items: {} as Record<number, PublicAvailability>, failures: {} as Record<number, string>, error: null as string | null, loading: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [expanded, setExpanded] = useState<number[]>([]);
  const [created, setCreated] = useState<{ reservations: CustomerReservation[]; equipmentIds: number[]; names: string[] } | null>(null);
  const submission = useRef(false);
  const alive = useRef(false);
  const confirmation = useRef<HTMLHeadingElement>(null);
  const [today, setToday] = useState(todayInMadrid);
  const range = { start_date: search.get('start_date') ?? '', end_date: search.get('end_date') ?? '' };
  if (selectionAccount !== customerId) {
    setSelectionAccount(customerId);
    setSelectionRestored(false);
    setExcluded([]);
    setRecoveryIds(null);
  } else if (!selectionRestored && customerId !== null && !saved.loading && !saved.error) {
    const previousSelection = readBatchReservationSelection(customerId, range, saved.ids);
    if (previousSelection) {
      setExcluded(saved.ids.filter((id) => !previousSelection.includes(id)));
      if (previousSelection.some((id) => !saved.ids.includes(id))) setRecoveryIds(previousSelection);
    }
    setSelectionRestored(true);
  }
  const validRange = completeDateRange(range) && range.start_date >= today;
  const idsKey = saved.ids.join(',');
  const productsKey = `${idsKey}:${revision}`;
  const productsReady = products.key === productsKey && !products.loading;
  const selected = recoveryIds ?? saved.ids.filter((id) => !excluded.includes(id));
  const operationScope = batchReservationScope(customerId, selected, range);
  const [operation, setOperation] = useState<{ scope: string | null; attempt: ReservationAttempt | null }>(() => ({ scope: operationScope, attempt: readReservationAttempt(operationScope) }));
  if (operation.scope !== operationScope) {
    setOperation({ scope: operationScope, attempt: readReservationAttempt(operationScope) });
    setCreated(null);
    setSubmitError(null);
  }
  const attempt = operation.scope === operationScope ? operation.attempt : null;
  const uncertain = attempt?.phase === 'uncertain';
  const completedAttempt = attempt?.phase === 'complete' ? attempt : null;
  const uncertainMessage = 'No hemos podido comprobar si se confirmó la reserva conjunta. Consulta Mis reservas o vuelve a confirmar de forma segura.';
  const selectedKnown = productsReady ? selected.filter((id) => !!products.items[id]?.equipment) : [];
  const calendar = useSharedAvailabilityCalendar(selectedKnown, range.start_date, revision);
  const availabilityKey = `${productsKey}:${range.start_date}:${range.end_date}:${today}`;
  const currentAvailability = availability.key === availabilityKey ? availability : null;
  const selectedAvailabilityError = selected.some((id) => !!currentAvailability?.failures[id]);
  const datesErrors = dateRangeErrors(range);
  if (range.start_date && range.start_date < today) datesErrors.start_date = 'Elige hoy o una fecha posterior para reservar.';
  if (range.start_date && !range.end_date && !errors.end_date) delete datesErrors.end_date;
  const visibleErrors = { ...datesErrors, ...errors };
  const allAvailable = validRange && selected.length > 0 && selected.length <= 50 && productsReady
    && selected.every((id) => !!products.items[id]?.equipment && currentAvailability?.items[id]?.available === true)
    && !currentAvailability?.loading && !currentAvailability?.error && !selectedAvailabilityError && !calendar.loading && !calendar.error
    && calendar.data?.can_book === true && !calendar.data.unavailable_end_dates?.includes(range.end_date)
    && !saved.loading && !saved.error && !saved.pending && Object.keys(visibleErrors).length === 0;

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (created && productsReady) confirmation.current?.focus(); }, [created, productsReady]);
  useEffect(() => {
    const refresh = () => setToday(todayInMadrid());
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('focus', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, []);

  useEffect(() => {
    if (saved.loading || saved.error) return;
    const controller = new AbortController();
    let active = true;
    const ids = idsKey ? idsKey.split(',').map(Number) : [];
    void Promise.resolve().then(async () => {
      if (!active) return;
      setProducts((previous) => ({ ...previous, loading: true }));
      const entries = await Promise.all(ids.map(async (id): Promise<[number, ProductResult]> => {
        try { return [id, { equipment: await api.getPublicEquipment(id, controller.signal), error: null }]; }
        catch (failure) {
          if (failure instanceof ApiError && failure.status === 404) return [id, { equipment: null, error: null }];
          if (controller.signal.aborted) throw failure;
          return [id, { equipment: null, error: failure instanceof Error ? failure.message : 'No se pudo cargar este equipo.' }];
        }
      }));
      if (active) setProducts({ key: productsKey, items: Object.fromEntries(entries), loading: false });
    }).catch(() => { /* Aborted navigation cannot update the next list. */ });
    return () => { active = false; controller.abort(); };
  }, [saved.loading, saved.error, idsKey, productsKey]);

  useEffect(() => {
    if (!productsReady || !validRange) return;
    const controller = new AbortController();
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setAvailability({ key: availabilityKey, items: {}, failures: {}, loading: true, error: null });
      const entries = await Promise.all(Object.entries(products.items).filter(([, result]) => result.equipment).map(async ([id]) => {
        try { return { id: Number(id), data: await api.getPublicAvailability(Number(id), { start_date: range.start_date, end_date: range.end_date }, controller.signal), error: null }; }
        catch (failure) { return { id: Number(id), data: null, error: failure instanceof Error ? failure.message : 'No se pudo comprobar la disponibilidad.' }; }
      }));
      if (active) setAvailability({ key: availabilityKey,
        items: Object.fromEntries(entries.flatMap((entry) => entry.data ? [[entry.id, entry.data]] : [])),
        failures: Object.fromEntries(entries.flatMap((entry) => entry.error ? [[entry.id, entry.error]] : [])), loading: false, error: null });
    }).catch((failure: unknown) => {
      if (active) setAvailability({ key: availabilityKey, items: {}, failures: {}, loading: false, error: failure instanceof Error ? failure.message : 'No se pudo comprobar la disponibilidad.' });
    });
    return () => { active = false; controller.abort(); };
  }, [productsReady, products.items, validRange, range.start_date, range.end_date, availabilityKey]);

  function resetConfirmation() { setCreated(null); setSubmitError(null); setErrors({}); }
  function resetOperation() {
    setOperation({ scope: null, attempt: null });
    resetConfirmation();
  }
  function prepareAnotherReservation() {
    const nextScope = recoveryIds ? batchReservationScope(customerId, saved.ids, range) : operationScope;
    if (!nextScope) { setRecoveryIds(null); setExcluded([]); resetConfirmation(); return; }
    const next = newReservationAttempt(nextScope);
    saveReservationAttempt(next);
    if (recoveryIds) { setRecoveryIds(null); setExcluded([]); }
    setOperation({ scope: nextScope, attempt: next });
    resetConfirmation();
    setRevision((value) => value + 1);
  }
  function changeDates(value: DateRange) {
    if (submission.current) return;
    resetOperation();
    setSearch(new URLSearchParams(rangeSearch(value).slice(1)), { replace: true });
  }
  function toggle(id: number) {
    if (submission.current) return;
    const nextExcluded = excluded.includes(id) ? excluded.filter((item) => item !== id) : [...excluded, id];
    resetOperation();
    setExcluded(nextExcluded);
  }
  async function remove(id: number) {
    if (submission.current) return;
    setActionError(null);
    try { await saved.change(id, false); resetOperation(); }
    catch (failure) { if (alive.current) setActionError(failure instanceof Error ? failure.message : 'No se pudo quitar el equipo.'); }
  }
  async function reserve() {
    if (submission.current) return;
    const validation = uncertain ? {} : dateRangeErrors(range, true);
    if (!uncertain && range.start_date && range.start_date < todayInMadrid()) validation.start_date = 'Elige hoy o una fecha posterior para reservar.';
    setErrors(validation);
    if (Object.keys(validation).length || (!allAvailable && !uncertain) || !operationScope) return;
    const sending: ReservationAttempt = { ...(attempt ?? newReservationAttempt(operationScope)), phase: 'uncertain' };
    saveReservationAttempt(sending);
    setOperation({ scope: operationScope, attempt: sending });
    submission.current = true; setPending(true); setSubmitError(null);
    try {
      const reservations = await api.createMyReservationsBatch({ equipment_ids: selected, ...range }, sending.key);
      const completed: ReservationAttempt = { ...sending, phase: 'complete', reservationIds: reservations.map((reservation) => reservation.id) };
      saveReservationAttempt(completed);
      if (alive.current) {
        setOperation({ scope: operationScope, attempt: completed });
        setCreated({ reservations, equipmentIds: selected, names: selected.map((id) => products.items[id]?.equipment?.name ?? `Equipo #${id}`) });
        setRevision((value) => value + 1);
      }
    } catch (failure) {
      const unknownOutcome = !(failure instanceof ApiError) || failure.status === 0 || failure.status === 401 || failure.status >= 500 || (failure.status >= 200 && failure.status < 300);
      if (!unknownOutcome) {
        const ready: ReservationAttempt = { ...sending, phase: 'ready' };
        saveReservationAttempt(ready);
        if (alive.current) setOperation({ scope: operationScope, attempt: ready });
      }
      if (!alive.current) return;
      if (failure instanceof ApiError && failure.status === 409) {
        setSubmitError('La disponibilidad ha cambiado. No se ha reservado ningún equipo. Estamos comprobando las fechas de nuevo; cambia el periodo o la selección.');
        setRevision((value) => value + 1);
      } else if (failure instanceof ApiError && failure.status === 404) {
        setSubmitError('Uno de los equipos ya no está disponible. No se ha reservado ningún equipo. Revisa tu lista.');
        saved.reload();
        setRevision((value) => value + 1);
      } else {
        setErrors(failure instanceof ApiError ? failure.fields : {});
        setSubmitError(failure instanceof ApiError && failure.status === 401 ? 'Tu sesión ha caducado. Accede de nuevo para reservar; tu lista y tus fechas se conservan.' : unknownOutcome ? uncertainMessage : failure instanceof Error ? failure.message : 'No se pudo confirmar la reserva conjunta.');
      }
    } finally { submission.current = false; if (alive.current) setPending(false); }
  }

  return <div className="saved-products-page">
    <PageHeader title="Mi lista" description="Guarda el equipo que necesitas, compara las fechas y reserva varios productos a la vez." action={<Link className="button button-secondary" to={`/catalogo${rangeSearch(range)}`}>Añadir equipos</Link>} />
    {saved.loading ? <p role="status">Cargando tu lista…</p> : saved.error ? <Notice tone="error">{saved.error} <button className="button button-secondary" type="button" onClick={saved.reload}>Volver a cargar mi lista</button></Notice> : saved.ids.length === 0 && !attempt ? <EmptyState title="Tu próximo proyecto empieza aquí" description="Guarda productos desde el catálogo para comparar su disponibilidad y reservarlos juntos." action={<Link className="button" to="/catalogo">Explorar el catálogo</Link>} /> : <>
      {actionError && <Notice tone="error">{actionError}</Notice>}
      {recoveryIds && <Notice tone="warning">Tu lista ha cambiado desde la reserva anterior. Consulta o recupera esa operación antes de preparar otra.</Notice>}
      <div className="saved-products-layout">
        <section className="saved-products-selection" aria-labelledby="saved-selection-title" aria-busy={!productsReady}>
          <div className="saved-products-selection-heading"><h2 id="saved-selection-title">Tus equipos guardados</h2><p>{recoveryIds ? 'Revisando tu reserva anterior' : `${selected.length} de ${saved.ids.length} seleccionados`}</p></div>
          <div className="saved-products-selection-actions"><button type="button" disabled={pending || saved.pending || !!recoveryIds || selected.length === saved.ids.length} onClick={() => { resetOperation(); setExcluded([]); }}>Seleccionar todos</button><button type="button" disabled={pending || saved.pending || !!recoveryIds || selected.length === 0} onClick={() => { resetOperation(); setExcluded([...saved.ids]); }}>Deseleccionar todos</button><button type="button" disabled={pending || saved.pending} onClick={() => { saved.reload(); }}>Actualizar mi lista</button></div>
          {!productsReady ? <p role="status">Cargando los equipos guardados…</p> : <ul className="saved-products-list">{saved.ids.map((id) => {
            const result = products.items[id];
            const item = result?.equipment;
            const available = currentAvailability?.items[id]?.available;
            const justBooked = !!created && created.reservations[created.equipmentIds.indexOf(id)]?.status === 'confirmed';
            const bookedRange = created?.reservations[0];
            const name = item?.name ?? `Equipo #${id}`;
            return <li key={id} className="saved-product">
              <div className="saved-product-overview">
                <label className="saved-product-select"><input type="checkbox" checked={selected.includes(id)} disabled={pending || saved.pending || !!recoveryIds} onChange={() => toggle(id)} aria-label={`Seleccionar ${name}`} /><span className="sr-only">Seleccionar {name}</span></label>
                {item && <Link className="saved-product-image" to={`/equipos/${id}${rangeSearch(range)}`} tabIndex={-1} aria-hidden="true"><ProductImage equipment={item} /></Link>}
                <div className="saved-product-info">{item && <p className="catalogue-category">{item.category}</p>}<h3>{item ? <Link to={`/equipos/${id}${rangeSearch(range)}`}>{name}</Link> : name}</h3>
                  {!item ? <p className="catalogue-availability is-unavailable">{result?.error ?? 'Este equipo ya no está en el catálogo. Puedes quitarlo de tu lista.'}</p> : <p className={`catalogue-availability${justBooked || available === true ? ' is-available' : available === false ? ' is-unavailable' : ''}`}>{justBooked && bookedRange ? `Reservado del ${formatDate(bookedRange.start_date)} al ${formatDate(bookedRange.end_date)}` : !validRange ? 'Elige fechas para comparar disponibilidad.' : !currentAvailability || currentAvailability.loading ? 'Comprobando tus fechas…' : currentAvailability.error || currentAvailability.failures[id] ? 'No se pudo comprobar la disponibilidad.' : available ? 'Disponible para todo el periodo' : 'No disponible para todo el periodo'}</p>}
                  <div className="saved-product-actions">{item && <button type="button" aria-expanded={expanded.includes(id)} aria-controls={`saved-calendar-${id}`} aria-label={`${expanded.includes(id) ? 'Ocultar' : 'Ver'} calendario de ${name}`} onClick={() => setExpanded((previous) => previous.includes(id) ? previous.filter((value) => value !== id) : [...previous, id])}>{expanded.includes(id) ? 'Ocultar calendario' : 'Ver calendario'}<span className="sr-only"> de {name}</span></button>}<button type="button" disabled={pending || saved.pending || !!recoveryIds} onClick={() => { void remove(id); }} aria-label={`Quitar ${name} de mi lista`}>Quitar</button>{result?.error && <button type="button" disabled={pending} onClick={() => setRevision((value) => value + 1)}>Reintentar cargar equipo</button>}</div>
                </div>
              </div>
              {item && expanded.includes(id) && <div id={`saved-calendar-${id}`} className="saved-product-calendar" role="region" aria-label={`Calendario de ${name}`}><ProductCalendar id={id} selectedDate={range.start_date} revision={revision} /></div>}
            </li>;
          })}</ul>}
        </section>
        <aside className="saved-products-booking" aria-labelledby="saved-booking-title">
          <h2 id="saved-booking-title">Unas fechas para todos</h2><p className="saved-products-booking-intro">El calendario combina la disponibilidad de los equipos seleccionados. Los días ocupados afectan al menos a uno.</p>
          {selectedKnown.length > 0 ? <AvailabilityCalendar title="Disponibilidad conjunta" calendar={calendar} {...(!created && !completedAttempt ? { range, onChange: changeDates, disabled: pending, errors: visibleErrors } : {})} /> : <p className="text-muted">Selecciona al menos un equipo del catálogo para consultar el calendario conjunto.</p>}
          {Object.keys(visibleErrors).length > 0 && <Notice tone="error" errors={visibleErrors}>Revisa las fechas del alquiler conjunto.</Notice>}
          {selected.length > 50 && <Notice tone="warning">Puedes reservar un máximo de 50 equipos a la vez. Reduce la selección.</Notice>}
          {!created && !completedAttempt && <div className="saved-products-summary" aria-live="polite">
            <strong>{selected.length} {selected.length === 1 ? 'equipo seleccionado' : 'equipos seleccionados'}</strong>
            {selected.length === 0 ? <p>Selecciona los equipos que quieres reservar.</p> : selectedKnown.length !== selected.length && productsReady ? <p>Hay equipos sin ficha disponible. Quítalos de la selección para continuar.</p> : !validRange ? <p>Elige la recogida y la devolución para comprobar si puedes alquilarlos juntos.</p> : !productsReady || !currentAvailability || currentAvailability.loading || calendar.loading ? <p role="status">Comprobando la disponibilidad conjunta…</p> : currentAvailability.error || selectedAvailabilityError || calendar.error ? <><p>No se pudo comprobar todo el periodo.</p><button type="button" className="button button-secondary" disabled={pending} onClick={() => setRevision((value) => value + 1)}>Reintentar disponibilidad</button></> : allAvailable ? <p className="catalogue-availability is-available">Todos disponibles del {formatDate(range.start_date)} al {formatDate(range.end_date)}.</p> : <p className="catalogue-availability is-unavailable">No todos están disponibles para estas fechas. Cambia el periodo o desmarca los equipos que no necesitas.</p>}
          </div>}
          {submitError && <Notice tone="error">{submitError} <Link to="/mis-reservas">Consultar Mis reservas</Link></Notice>}
          {uncertain && !pending && !submitError && <Notice tone="warning">{uncertainMessage} <Link to="/mis-reservas">Consultar Mis reservas</Link></Notice>}
          {created ? <section className="saved-products-confirmation" aria-label="Resultado de la reserva conjunta"><Notice tone={created.reservations.every((reservation) => reservation.status === 'confirmed') ? 'success' : 'info'}>{created.reservations.every((reservation) => reservation.status === 'confirmed') ? 'Todos los equipos se han reservado.' : 'Esta operación ya estaba registrada. Consulta el estado actual de cada reserva.'}</Notice><h3 ref={confirmation} tabIndex={-1}>{created.reservations.length} {created.reservations.every((reservation) => reservation.status === 'confirmed') ? created.reservations.length === 1 ? 'reserva confirmada' : 'reservas confirmadas' : created.reservations.length === 1 ? 'reserva registrada' : 'reservas registradas'}</h3><p>Del {formatDate(created.reservations[0]!.start_date)} al {formatDate(created.reservations[0]!.end_date)}. Devolución no incluida.</p><ul>{created.reservations.map((reservation, index) => <li key={reservation.id}><Link to={`/mis-reservas/${reservation.id}`}>Reserva #{reservation.id} · {created.names[index]}</Link></li>)}</ul><Link className="button" to="/mis-reservas">Ver mis reservas</Link><button type="button" className="button button-secondary" onClick={prepareAnotherReservation}>Preparar otra reserva</button><p className="product-confirmation-note">Tus equipos siguen guardados en Mi lista.</p></section> : completedAttempt ? <section className="saved-products-confirmation" aria-label="Reserva conjunta registrada"><Notice>Ya registraste una reserva conjunta con esta selección y estas fechas. Consulta su estado antes de preparar otra.</Notice><ul>{completedAttempt.reservationIds.map((id) => <li key={id}><Link to={`/mis-reservas/${id}`}>Ver reserva #{id}</Link></li>)}</ul><button type="button" className="button button-secondary" onClick={prepareAnotherReservation}>Preparar otra reserva</button></section> : <><button type="button" className="button saved-products-confirm-button" disabled={(!allAvailable && !uncertain) || pending} onClick={() => { void reserve(); }}>{pending ? 'Confirmando todos los equipos…' : uncertain ? 'Volver a confirmar de forma segura' : `Reservar ${selected.length || ''} ${selected.length === 1 ? 'equipo' : 'equipos'} a la vez`}</button><p className="product-confirmation-note">Se confirman todos juntos. Si un equipo deja de estar disponible, no se reserva ninguno. El día de devolución no se incluye.</p></>}
        </aside>
      </div>
    </>}
  </div>;
}
