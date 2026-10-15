import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, ApiError, type CustomerReservation, type DateRange, type PublicAvailability, type PublicEquipment } from '../api/client';
import { useAuth } from '../auth/context';
import { Notice, StatusBadge } from '../components/ui';
import { formatDate } from '../lib/dates';
import { completeDateRange, dateRangeErrors, rangeSearch, todayInMadrid } from './dateRange';
import { ProductImage } from './ProductImage';
import { SaveProductButton } from './SaveProductButton';
import { AvailabilityCalendar } from './AvailabilityCalendar';
import { useAvailabilityCalendar } from './useAvailabilityCalendar';
import { productCatalogueReturn } from './catalogueNavigation';
import { newReservationAttempt, readReservationAttempt, reservationScope, saveReservationAttempt, type ReservationAttempt } from './reservationAttempt';
import './catalogue.css';

interface AvailabilityState {
  key: string;
  data: PublicAvailability | null;
  loading: boolean;
  error: string | null;
}

function Product({ equipmentId }: { equipmentId: number }) {
  const [search, setSearch] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { session, checking } = useAuth();
  const [equipment, setEquipment] = useState<PublicEquipment | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [equipmentRetry, setEquipmentRetry] = useState(0);
  const [availability, setAvailability] = useState<AvailabilityState>({ key: '', data: null, loading: false, error: null });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [created, setCreated] = useState<CustomerReservation | null>(null);
  const confirmationHeading = useRef<HTMLHeadingElement>(null);
  const submissionInFlight = useRef(false);
  const [availabilityRetry, setAvailabilityRetry] = useState(0);
  const range = { start_date: search.get('start_date') ?? '', end_date: search.get('end_date') ?? '' };
  const customerId = session?.role === 'customer' ? session.user?.id ?? null : null;
  const operationScope = reservationScope(customerId, { equipment_id: equipmentId, ...range });
  const [operation, setOperation] = useState<{ scope: string | null; attempt: ReservationAttempt | null }>(() => ({ scope: operationScope, attempt: readReservationAttempt(operationScope) }));
  if (operation.scope !== operationScope) {
    setOperation({ scope: operationScope, attempt: readReservationAttempt(operationScope) });
    setCreated(null);
    setSubmitError(null);
  }
  const attempt = operation.scope === operationScope ? operation.attempt : null;
  const uncertain = attempt?.phase === 'uncertain';
  const completedAttempt = attempt?.phase === 'complete' ? attempt : null;
  const uncertainMessage = 'No hemos podido comprobar si se confirmó. Consulta Mis reservas o vuelve a confirmar de forma segura.';
  const catalogueReturn = productCatalogueReturn(location.state, search.get('catalogue'), `/catalogo${rangeSearch(range)}`);
  const validRange = completeDateRange(range);
  const rangeKey = `${equipmentId}:${range.start_date}:${range.end_date}`;
  const currentAvailability = availability.key === rangeKey ? availability : null;
  const calendar = useAvailabilityCalendar(equipmentId, range.start_date, availabilityRetry, true);
  const rangeErrors = dateRangeErrors(range);
  if (range.start_date && range.start_date < todayInMadrid()) rangeErrors.start_date = 'Elige hoy o una fecha posterior para reservar.';
  const visibleErrors = { ...rangeErrors, ...errors };
  if (range.start_date && !range.end_date && !rangeErrors.start_date && !errors.end_date) delete visibleErrors.end_date;
  const unavailableCalendarRange = calendar.data?.unavailable_end_dates?.includes(range.end_date) === true;
  const checkedAvailable = validRange && currentAvailability?.data?.available === true && !calendar.loading
    && calendar.data?.can_book === true && !unavailableCalendarRange && Object.keys(visibleErrors).length === 0;
  const availabilityLoading = validRange && (!currentAvailability || currentAvailability.loading || calendar.loading);

  useEffect(() => { if (created) confirmationHeading.current?.focus(); }, [created]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    void api.getPublicEquipment(equipmentId, controller.signal).then((result) => {
      if (current) { setEquipment(result); setLoadError(null); }
    }, (failure: unknown) => {
      if (current) setLoadError(failure instanceof ApiError && failure.status === 404 ? 'Este equipo no está disponible en el catálogo.' : failure instanceof Error ? failure.message : 'No se pudo cargar el equipo.');
    });
    return () => { current = false; controller.abort(); };
  }, [equipmentId, equipmentRetry]);

  useEffect(() => {
    if (!equipment || !validRange) return;
    const controller = new AbortController();
    let current = true;
    const dates = { start_date: range.start_date, end_date: range.end_date };
    void Promise.resolve().then(async () => {
      if (!current) return;
      setAvailability({ key: rangeKey, data: null, loading: true, error: null });
      const result = await api.getPublicAvailability(equipmentId, dates, controller.signal);
      if (current) setAvailability({ key: rangeKey, data: result, loading: false, error: null });
    }).catch((failure: unknown) => {
      if (current) setAvailability({ key: rangeKey, data: null, loading: false, error: failure instanceof Error ? failure.message : 'No se pudo consultar la disponibilidad.' });
    });
    return () => { current = false; controller.abort(); };
  }, [equipment, equipmentId, range.start_date, range.end_date, rangeKey, validRange, availabilityRetry]);

  function changeDates(value: DateRange) {
    setOperation({ scope: null, attempt: null });
    setErrors({});
    setSubmitError(null);
    setCreated(null);
    setSearch((previous) => {
      const next = new URLSearchParams(previous);
      for (const name of ['start_date', 'end_date'] as const) {
        if (value[name]) next.set(name, value[name]); else next.delete(name);
      }
      return next;
    }, { replace: true, state: location.state });
  }

  function prepareAnotherReservation() {
    if (!operationScope) return;
    const next = newReservationAttempt(operationScope);
    saveReservationAttempt(next);
    setOperation({ scope: operationScope, attempt: next });
    setCreated(null);
    setErrors({});
    setSubmitError(null);
    setAvailabilityRetry((value) => value + 1);
  }

  async function reserve() {
    if (submissionInFlight.current) return;
    const validation = uncertain ? {} : dateRangeErrors(range, true);
    if (!uncertain && completeDateRange(range) && range.start_date < todayInMadrid()) validation.start_date = 'Elige hoy o una fecha posterior para reservar.';
    setErrors(validation);
    setSubmitError(null);
    if (Object.keys(validation).length > 0 || (!checkedAvailable && !uncertain) || checking) return;
    if (!session) {
      const destinationQuery = new URLSearchParams(rangeSearch(range));
      if (location.state || search.has('catalogue')) destinationQuery.set('catalogue', catalogueReturn.path);
      const destination = `/equipos/${equipmentId}${destinationQuery.size ? `?${destinationQuery}` : ''}`;
      void navigate(`/acceso?next=${encodeURIComponent(destination)}`);
      return;
    }
    if (session.role !== 'customer' || !operationScope) return;
    const activeAttempt = attempt ?? newReservationAttempt(operationScope);
    const sending: ReservationAttempt = { ...activeAttempt, phase: 'uncertain' };
    saveReservationAttempt(sending);
    setOperation({ scope: operationScope, attempt: sending });
    submissionInFlight.current = true;
    setPending(true);
    try {
      const reservation = await api.createMyReservation({ equipment_id: equipmentId, start_date: range.start_date, end_date: range.end_date }, sending.key);
      const completed: ReservationAttempt = { ...sending, phase: 'complete', reservationIds: [reservation.id] };
      saveReservationAttempt(completed);
      setOperation({ scope: operationScope, attempt: completed });
      setCreated(reservation);
      setAvailabilityRetry((value) => value + 1);
    } catch (failure) {
      const unknownOutcome = !(failure instanceof ApiError) || failure.status === 0 || failure.status === 401 || failure.status >= 500 || (failure.status >= 200 && failure.status < 300);
      if (!unknownOutcome) {
        const ready: ReservationAttempt = { ...sending, phase: 'ready' };
        saveReservationAttempt(ready);
        setOperation({ scope: operationScope, attempt: ready });
      }
      if (failure instanceof ApiError && failure.status === 409) {
        setAvailability({ key: rangeKey, data: null, loading: false, error: null });
        setSubmitError('La disponibilidad ha cambiado y estas fechas ya no se pueden confirmar. Selecciona otro periodo o consulta otro equipo.');
        setAvailabilityRetry((value) => value + 1);
      } else if (failure instanceof ApiError && failure.status === 503) {
        setSubmitError(`El sistema está ocupado temporalmente. ${uncertainMessage}`);
      } else if (failure instanceof ApiError && failure.status === 401) {
        setSubmitError('Tu sesión ha caducado. Accede de nuevo para confirmar; tus fechas se conservan.');
      } else if (failure instanceof ApiError && failure.status === 403) {
        setSubmitError('Tu cuenta no tiene permiso para crear esta reserva.');
      } else if (failure instanceof ApiError && failure.status === 404) {
        setSubmitError('Este equipo ya no está disponible en el catálogo. Vuelve al catálogo para elegir otro.');
        setAvailability({ key: rangeKey, data: null, loading: false, error: null });
      } else {
        setErrors(failure instanceof ApiError ? failure.fields : {});
        setSubmitError(unknownOutcome ? uncertainMessage : failure instanceof Error ? failure.message : 'No se pudo confirmar la reserva.');
      }
    } finally { submissionInFlight.current = false; setPending(false); }
  }

  const catalogPath = catalogueReturn.path;
  if (loadError && !uncertain && !completedAttempt) return <><Link className="back-link" to={catalogPath} state={{ catalogueRestore: catalogueReturn }}>Volver al catálogo</Link><h1>Equipo no disponible</h1><Notice tone="error">{loadError}</Notice><button type="button" className="button button-secondary" onClick={() => setEquipmentRetry((value) => value + 1)}>Volver a cargar</button></>;
  if (loadError && (uncertain || completedAttempt)) return <>
    <Link className="back-link" to={catalogPath} state={{ catalogueRestore: catalogueReturn }}>Volver al catálogo</Link><h1>Tu reserva</h1>
    {completedAttempt ? <><Notice>Ya registraste una reserva con estas fechas.</Notice><Link className="button" to={`/mis-reservas/${completedAttempt.reservationIds[0]}`}>Ver mi reserva</Link></> : <><Notice tone="warning">{uncertainMessage}</Notice><Link className="button button-secondary" to="/mis-reservas">Consultar Mis reservas</Link><button type="button" className="button" disabled={pending} onClick={() => { void reserve(); }}>{pending ? 'Confirmando reserva…' : 'Volver a confirmar de forma segura'}</button>{submitError && <Notice tone="error">{submitError}</Notice>}</>}
  </>;
  if (!equipment) return <p role="status" className="catalogue-loading">Cargando equipo…</p>;

  return <>
    <Link className="back-link" to={catalogPath} state={{ catalogueRestore: catalogueReturn }}>Volver al catálogo</Link>
    <div className="product-layout">
      <div className="product-overview">
        <header className="product-heading"><p className="catalogue-category">{equipment.category}</p><h1>{equipment.name}</h1><SaveProductButton id={equipment.id} name={equipment.name} /></header>
        <ProductImage equipment={equipment} className="product-image" eager />
        <section className="product-description" aria-labelledby="product-description-title"><h2 id="product-description-title">Sobre este equipo</h2><p>{equipment.public_description || 'Consulta sus características y elige las fechas de tu proyecto.'}</p></section>
        <section className="product-specifications" aria-labelledby="product-specifications-title"><h2 id="product-specifications-title">Características técnicas</h2>{Object.keys(equipment.technical_specs).length ? <dl>{Object.entries(equipment.technical_specs).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : <p className="text-muted">Este equipo aún no tiene características publicadas.</p>}</section>
      </div>
      <aside className="product-booking" aria-labelledby="product-booking-title">
        <h2 id="product-booking-title">Reserva tus fechas</h2>
        <p className="product-booking-intro">Consulta los días disponibles y elige tu recogida y devolución en el calendario.</p>
        <AvailabilityCalendar calendar={calendar} {...(!created && !completedAttempt ? { range, onChange: changeDates, disabled: pending, errors: visibleErrors } : {})} />
        {created ? <section className="product-confirmation" aria-label="Resultado de tu reserva"><Notice tone={created.status === 'confirmed' ? 'success' : 'info'}>{created.status === 'confirmed' ? 'Tu reserva se ha confirmado.' : 'Esta reserva está cancelada. Puedes consultar su historial.'}</Notice><h3 ref={confirmationHeading} tabIndex={-1}>Reserva #{created.id}</h3><StatusBadge kind={created.status} /><p>{formatDate(created.start_date)} al {formatDate(created.end_date)}<br /><span className="text-muted">Día de devolución no incluido.</span></p><Link className="button" to={`/mis-reservas/${created.id}`}>Ver mi reserva</Link><button type="button" className="button button-secondary" onClick={prepareAnotherReservation}>Preparar otra reserva</button><Link className="product-secondary-link" to={catalogPath} state={{ catalogueRestore: catalogueReturn }}>Seguir explorando</Link></section> : completedAttempt ? <section className="product-confirmation" aria-label="Reserva registrada"><Notice>Ya registraste una reserva con estas fechas. Consulta su estado antes de preparar otra.</Notice><Link className="button" to={`/mis-reservas/${completedAttempt.reservationIds[0]}`}>Ver mi reserva</Link><button type="button" className="button button-secondary" onClick={prepareAnotherReservation}>Preparar otra reserva</button></section> : <>
          {Object.keys(visibleErrors).length > 0 && <Notice tone="error" errors={visibleErrors}>Revisa las fechas de la reserva.</Notice>}
          {validRange && <div className="product-availability" aria-live="polite">
            {availabilityLoading ? <p role="status">Comprobando tus fechas…</p> : currentAvailability?.error ? <><Notice tone="error">{currentAvailability.error}</Notice><button type="button" className="button button-secondary" onClick={() => setAvailabilityRetry((value) => value + 1)}>Reintentar disponibilidad</button></> : calendar.data?.can_book === false ? <p className="catalogue-availability is-unavailable">El equipo no admite nuevas reservas en este momento. Consulta otro equipo.</p> : currentAvailability?.data?.available === true && calendar.data && !unavailableCalendarRange ? <p className="catalogue-availability is-available">Disponible del {formatDate(range.start_date)} al {formatDate(range.end_date)}.</p> : currentAvailability?.data?.available === false || unavailableCalendarRange ? <p className="catalogue-availability is-unavailable">{calendar.data?.can_book === true ? 'No hay disponibilidad para todo este periodo. Selecciona otras fechas o consulta otro equipo.' : 'No se puede reservar este periodo. Consulta otras fechas o vuelve al catálogo para elegir otro equipo.'}</p> : null}
          </div>}
          {submitError && <Notice tone="error">{submitError}</Notice>}
          {uncertain && !pending && !submitError && <Notice tone="warning">{uncertainMessage}</Notice>}
          {uncertain && <Link className="product-secondary-link" to="/mis-reservas">Consultar Mis reservas</Link>}
          {session?.role === 'admin' ? <div className="product-admin-action"><p>Gestiona las reservas desde tu panel de administración.</p><Link className="button" to="/admin">Ir al panel</Link></div> : checking ? <p role="status">Comprobando tu cuenta…</p> : <>
            <button type="button" className="button product-reserve-button" disabled={(!checkedAvailable && !uncertain) || pending} onClick={() => { void reserve(); }}>{pending ? 'Confirmando reserva…' : uncertain ? 'Volver a confirmar de forma segura' : session ? 'Confirmar reserva' : 'Acceder para reservar'}</button>
            <p className="product-confirmation-note">{session ? 'Al confirmar se comprobará de nuevo la disponibilidad.' : 'Conservaremos el equipo y tus fechas al acceder. Después podrás confirmar la reserva.'}</p>
          </>}
        </>}
      </aside>
    </div>
  </>;
}

export function ProductPage() {
  const { id } = useParams();
  const equipmentId = Number(id);
  if (!Number.isSafeInteger(equipmentId) || equipmentId <= 0) return <><h1>Equipo no encontrado</h1><Notice tone="error">El equipo solicitado no existe.</Notice><Link to="/catalogo">Volver al catálogo</Link></>;
  return <Product key={equipmentId} equipmentId={equipmentId} />;
}
