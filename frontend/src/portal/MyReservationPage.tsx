import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { CustomerReservation, PublicAvailability } from '../types/api';
import { Field, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';
import { todayInMadrid } from './dateRange';
import './account.css';

export default function MyReservationPage() {
  const { id } = useParams();
  return <ReservationDetails key={id} reservationId={Number(id)} />;
}

function ReservationDetails({ reservationId }: { reservationId: number }) {
  const location = useLocation();
  const resource = useResource(useCallback(async () => {
    if (!Number.isSafeInteger(reservationId) || reservationId <= 0) throw new Error('La reserva indicada no existe.');
    const reservation = await api.getMyReservation(reservationId);
    try {
      const equipment = await api.getPublicEquipment(reservation.equipment_id);
      return { reservation, equipmentName: equipment.name, equipmentAvailable: true };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return { reservation, equipmentName: `Equipo #${reservation.equipment_id} (ficha no disponible)`, equipmentAvailable: false };
      throw error;
    }
  }, [reservationId]));
  const [savedReservation, setSavedReservation] = useState<CustomerReservation | null>(null);
  const [updatedAvailability, setUpdatedAvailability] = useState<PublicAvailability | null>(null);
  const [availabilityError, setAvailabilityError] = useState(false);
  const [confirmingCancellation, setConfirmingCancellation] = useState(false);
  const [showIncidentForm, setShowIncidentForm] = useState(false);
  const [incidentCreatedFor, setIncidentCreatedFor] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const cancellation = useFormFeedback();
  const incident = useFormFeedback();
  const confirmButton = useRef<HTMLButtonElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const detailsHeading = useRef<HTMLHeadingElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const reportButton = useRef<HTMLButtonElement>(null);
  const previousConfirmation = useRef(false);
  const previousIncidentForm = useRef(false);
  const cancellationInFlight = useRef(false);

  useEffect(() => {
    if (confirmingCancellation) confirmButton.current?.focus();
    else if (previousConfirmation.current) cancelButton.current?.focus();
    previousConfirmation.current = confirmingCancellation;
  }, [confirmingCancellation]);
  useEffect(() => {
    if (showIncidentForm) titleInput.current?.focus();
    else if (previousIncidentForm.current) reportButton.current?.focus();
    previousIncidentForm.current = showIncidentForm;
  }, [showIncidentForm]);
  useEffect(() => {
    if (savedReservation?.id === reservationId && savedReservation.status === 'cancelled') detailsHeading.current?.focus();
  }, [savedReservation, reservationId]);

  const data = resource.data?.reservation.id === reservationId ? resource.data : null;
  const reservation = savedReservation?.id === reservationId ? savedReservation : data?.reservation;
  const canCancel = reservation?.status === 'confirmed' && todayInMadrid() < reservation.start_date;
  const created = typeof location.state === 'object' && location.state !== null && 'created' in location.state && location.state.created === true;

  async function cancelReservation() {
    if (cancellationInFlight.current) return;
    cancellationInFlight.current = true;
    cancellation.clear();
    cancellation.setPending(true);
    try {
      const updated = await api.cancelMyReservation(reservationId);
      setSavedReservation(updated);
      setConfirmingCancellation(false);
      setShowIncidentForm(false);
      resource.reload();
      try {
        setUpdatedAvailability(await api.getPublicAvailability(updated.equipment_id, { start_date: updated.start_date, end_date: updated.end_date }));
        setAvailabilityError(false);
      } catch {
        setAvailabilityError(true);
      }
    } catch (error) {
      cancellation.setFailure(error);
      resource.reload();
    } finally {
      cancellationInFlight.current = false;
      cancellation.setPending(false);
    }
  }

  async function createIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (incident.pending) return;
    incident.clear();
    const errors: Record<string, string> = {};
    if (!title.trim()) errors.title = 'Escribe un título para el problema.';
    if (!description.trim()) errors.description = 'Describe qué ha ocurrido con el equipo.';
    if (Object.keys(errors).length) { incident.setValidation(errors); return; }
    incident.setPending(true);
    try {
      await api.createMyIncident(reservationId, { title: title.trim(), description: description.trim() });
      setIncidentCreatedFor(reservationId);
      setShowIncidentForm(false);
      setTitle('');
      setDescription('');
    } catch (error) {
      incident.setFailure(error);
    } finally {
      incident.setPending(false);
    }
  }

  return <div className="portal-account">
    <Link className="back-link" to="/mis-reservas">← Mis reservas</Link>
    <PageHeader title={reservation ? `Reserva #${reservation.id}` : 'Detalle de tu reserva'} description="Las fechas de alquiler se cuentan por días completos." />
    {resource.loading && <p role="status">Cargando tu reserva…</p>}
    {resource.error && <Notice tone="error">{resource.error} <button className="button button-secondary" type="button" onClick={resource.reload}>Reintentar</button></Notice>}
    {reservation && data && <div className="portal-account-detail">
      <div className="portal-account-main">
        {savedReservation?.id === reservationId && savedReservation.status === 'cancelled'
          ? <><Notice tone="success">Reserva cancelada. Puedes seguir consultando su historial.</Notice>{updatedAvailability && <p className="portal-account-muted">Disponibilidad actualizada: {updatedAvailability.available ? 'el periodo vuelve a estar disponible.' : 'el equipo no está disponible para ese periodo; consulta su ficha para elegir otra opción.'}</p>}{availabilityError && <Notice tone="warning">La cancelación se ha guardado. No se pudo actualizar la disponibilidad; vuelve a la ficha del equipo para consultarla.</Notice>}</>
          : created && <Notice tone="success">Reserva #{reservation.id} confirmada. El equipo está reservado para las fechas indicadas.</Notice>}
        <section className="portal-account-panel" aria-labelledby="reservation-details-heading">
          <div className="portal-account-panel-heading"><h2 ref={detailsHeading} tabIndex={-1} id="reservation-details-heading">Datos de tu reserva</h2><StatusBadge kind={reservation.status} /></div>
          <h3 className="portal-account-equipment">{data.equipmentAvailable ? <Link to={`/equipos/${reservation.equipment_id}`}>{data.equipmentName}</Link> : data.equipmentName}</h3>
          <dl className="portal-account-facts">
            <div><dt>Referencia</dt><dd>#{reservation.id}</dd></div>
            <div><dt>Inicio incluido</dt><dd><time dateTime={reservation.start_date}>{formatDate(reservation.start_date)}</time></dd></div>
            <div><dt>Fin excluido</dt><dd><time dateTime={reservation.end_date}>{formatDate(reservation.end_date)}</time></dd></div>
          </dl>
          <p className="portal-account-muted">El día de fin ya no forma parte de tu alquiler.</p>
        </section>
        {reservation.status === 'confirmed' && <section className="portal-account-panel" aria-labelledby="report-problem-heading">
          <h2 id="report-problem-heading">¿Hay algún problema con el equipo?</h2>
          <p>Cuéntanos qué ha ocurrido. Podrás seguir tu aviso y consultar la respuesta en Mis incidencias.</p>
          {incidentCreatedFor === reservationId && <Notice tone="success">Aviso enviado. <Link to="/mis-incidencias">Consultar mis incidencias</Link></Notice>}
          {showIncidentForm ? <form className="portal-account-incident-form" onSubmit={(event) => { void createIncident(event); }} noValidate>
            {incident.message && <Notice tone="error" errors={incident.errors}>{incident.message}</Notice>}
            <Field name="title" label="Título del problema" error={incident.errors.title}><input ref={titleInput} name="title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={160} /></Field>
            <Field name="description" label="Descripción del problema" hint="Explica qué sucede y cómo lo has detectado." error={incident.errors.description}><textarea name="description" value={description} onChange={(event) => setDescription(event.target.value)} required maxLength={2000} rows={5} /></Field>
            <div className="inline-actions"><button className="button" type="submit" disabled={incident.pending}>{incident.pending ? 'Enviando aviso…' : 'Enviar aviso'}</button><button className="button button-secondary" type="button" disabled={incident.pending} onClick={() => setShowIncidentForm(false)}>Volver a la reserva</button></div>
          </form> : <button ref={reportButton} className="button button-secondary" type="button" onClick={() => { incident.clear(); setShowIncidentForm(true); }}>Informar de un problema</button>}
        </section>}
      </div>
      {reservation.status === 'confirmed' && <aside className="portal-account-panel portal-account-cancellation" aria-label="Cancelación de tu reserva">
        <h2>Cancelar reserva</h2>
        {cancellation.message && <Notice tone="error" errors={cancellation.errors}>{cancellation.message}</Notice>}
        {canCancel ? <>
          <p>Puedes cancelar hasta el día anterior al inicio, según la fecha de Madrid. La reserva permanecerá en tu historial.</p>
          {confirmingCancellation ? <fieldset className="portal-account-confirmation"><legend>Confirmar cancelación</legend><p>¿Quieres cancelar la reserva #{reservation.id}?</p><button ref={confirmButton} className="button button-danger" type="button" disabled={cancellation.pending} onClick={() => { void cancelReservation(); }}>{cancellation.pending ? 'Cancelando…' : 'Sí, cancelar reserva'}</button><button className="button button-secondary" type="button" disabled={cancellation.pending} onClick={() => { setConfirmingCancellation(false); cancellation.clear(); }}>Conservar reserva</button></fieldset>
            : <button ref={cancelButton} className="button button-secondary" type="button" onClick={() => { cancellation.clear(); setConfirmingCancellation(true); }}>Cancelar reserva</button>}
        </> : <p>El plazo de cancelación ha terminado: solo puedes cancelar antes del día de inicio, según la fecha de Madrid.</p>}
      </aside>}
    </div>}
  </div>;
}
