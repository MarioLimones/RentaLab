import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Reservation } from '../api/client';
import { Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';
import { reservationOrigin, reservationOwner } from '../admin/reservationLabels';

export default function ReservationDetailPage() {
  const { id } = useParams();
  return <ReservationDetails key={id} reservationId={Number(id)} />;
}

function ReservationDetails({ reservationId }: { reservationId: number }) {
  const location = useLocation();
  const resource = useResource(useCallback(async () => {
    if (!Number.isSafeInteger(reservationId) || reservationId <= 0) throw new Error('La reserva indicada no existe.');
    const reservation = await api.getReservation(reservationId);
    const equipment = await api.getEquipment(reservation.equipment_id);
    return { reservation, equipment };
  }, [reservationId]));
  const [savedReservation, setSavedReservation] = useState<Reservation | null>(null);
  const [confirming, setConfirming] = useState(false);
  const feedback = useFormFeedback();
  const confirmButton = useRef<HTMLButtonElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (confirming) confirmButton.current?.focus();
    else cancelButton.current?.focus();
  }, [confirming]);

  useEffect(() => {
    if (savedReservation?.id === reservationId && savedReservation.status === 'cancelled') {
      detailHeading.current?.focus();
    }
  }, [savedReservation, reservationId]);

  async function cancelReservation() {
    if (feedback.pending) return;
    feedback.clear();
    feedback.setPending(true);
    try {
      const response = await api.cancelReservation(reservationId);
      setSavedReservation(response);
      setConfirming(false);
      resource.reload();
    } catch (error) {
      feedback.setFailure(error);
    } finally {
      feedback.setPending(false);
    }
  }

  const reservation = savedReservation?.id === reservationId ? savedReservation
    : resource.data?.reservation.id === reservationId ? resource.data.reservation : undefined;
  const equipment = resource.data?.reservation.id === reservationId ? resource.data.equipment : undefined;
  const created = typeof location.state === 'object' && location.state !== null
    && 'created' in location.state && location.state.created === true;

  return <>
    <Link className="back-link" to="/admin/reservas">← Reservas</Link>
    <PageHeader title={reservation ? `Reserva #${reservation.id}` : 'Detalle de reserva'} description="El historial mantiene el cliente, las fechas y la referencia también después de cancelar." />
    {resource.loading && <p role="status">Cargando reserva…</p>}
    {resource.error && <Notice tone="error">{resource.error} <button className="button button-secondary" type="button" onClick={resource.reload}>Reintentar</button></Notice>}
    {reservation && equipment && <div className="stack">
      {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
      {savedReservation?.id === reservation.id && savedReservation.status === 'cancelled'
        ? <Notice tone="success">Reserva cancelada. Se conserva su historial y deja de bloquear el intervalo.</Notice>
        : created && <Notice tone="success">Reserva creada y confirmada.</Notice>}
      <section className="panel">
        <div className="panel-header"><h2 ref={detailHeading} tabIndex={-1}>Datos de la reserva</h2><StatusBadge kind={reservation.status} /></div>
        <dl className="detail-list">
          <div><dt>Equipo</dt><dd><Link to={`/admin/equipos/${equipment.id}`}>{equipment.code} · {equipment.name}</Link></dd></div>
          <div><dt>Cliente</dt><dd>{reservation.customer_name}</dd></div>
          <div><dt>Correo</dt><dd>{reservation.customer_email}</dd></div>
          <div><dt>Propietario de cuenta</dt><dd>{reservation.customer_user_id ? <Link to={`/admin/reservas?customer_user_id=${reservation.customer_user_id}`}>{reservationOwner(reservation)}</Link> : reservationOwner(reservation)}</dd></div>
          <div><dt>Origen</dt><dd>{reservationOrigin(reservation)}</dd></div>
          <div><dt>Inicio incluido</dt><dd>{formatDate(reservation.start_date)}</dd></div>
          <div><dt>Fin excluido</dt><dd>{formatDate(reservation.end_date)}</dd></div>
          <div><dt>Referencia externa</dt><dd>{reservation.external_reference ?? 'Sin referencia externa'}</dd></div>
        </dl>
      </section>
      {reservation.status === 'confirmed' && <section className="panel stack" aria-label="Cancelación de reserva">
        <h2>Cancelar reserva</h2>
        <p>La cancelación conserva todos los datos y se reflejará en la cuenta del propietario al volver a consultar. Otras reservas, incidencias o el estado del equipo pueden seguir impidiendo nuevos alquileres.</p>
        {confirming ? <fieldset className="stack">
          <legend>Confirmar cancelación</legend>
          <p>¿Quieres cancelar la reserva #{reservation.id}? Su historial se conservará.</p>
          <div className="inline-actions">
            <button ref={confirmButton} className="button button-danger" type="button" disabled={feedback.pending} onClick={() => { void cancelReservation(); }}>{feedback.pending ? 'Cancelando…' : 'Sí, cancelar reserva'}</button>
            <button className="button button-secondary" type="button" disabled={feedback.pending} onClick={() => { setConfirming(false); feedback.clear(); }}>Volver</button>
          </div>
        </fieldset> : <div><button ref={cancelButton} className="button button-danger" type="button" onClick={() => { feedback.clear(); setConfirming(true); }}>Cancelar reserva</button></div>}
      </section>}
    </div>}
  </>;
}
