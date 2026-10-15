import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { ReservationFilters, ReservationOrigin, ReservationStatus } from '../api/client';
import { reservationOrigin, reservationOrigins, reservationOwner } from '../admin/reservationLabels';
import { EmptyState, Field, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';

export default function ReservationsPage() {
  const [search] = useSearchParams();
  const initialOwner = search.get('customer_user_id') ?? '';
  const validInitialOwner = /^[1-9]\d*$/.test(initialOwner) && Number.isSafeInteger(Number(initialOwner)) ? initialOwner : '';
  const [customer, setCustomer] = useState('');
  const [customerUserId, setCustomerUserId] = useState(validInitialOwner);
  const [origin, setOrigin] = useState<ReservationOrigin | ''>('');
  const [equipmentId, setEquipmentId] = useState('');
  const [status, setStatus] = useState<ReservationStatus | ''>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [filters, setFilters] = useState<ReservationFilters>(validInitialOwner ? { customer_user_id: Number(validInitialOwner) } : {});
  const equipment = useResource(useCallback(() => api.listEquipment(), []));
  const reservations = useResource(useCallback(() => api.listReservations(filters), [filters]));
  const feedback = useFormFeedback();

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    feedback.clear();
    const errors: Record<string, string> = {};
    if (customerUserId && (!/^[1-9]\d*$/.test(customerUserId) || !Number.isSafeInteger(Number(customerUserId)))) errors.customer_user_id = 'Indica un identificador de cuenta positivo.';
    if (Boolean(startDate) !== Boolean(endDate)) {
      errors[startDate ? 'end_date' : 'start_date'] = 'Indica ambas fechas para filtrar por intervalo.';
    } else if (startDate && endDate <= startDate) {
      errors.end_date = 'La fecha de fin debe ser posterior al inicio.';
    }
    if (Object.keys(errors).length > 0) {
      feedback.setValidation(errors);
      return;
    }
    setFilters({
      ...(customer.trim() ? { customer: customer.trim() } : {}),
      ...(customerUserId ? { customer_user_id: Number(customerUserId) } : {}),
      ...(origin ? { origin } : {}),
      ...(equipmentId ? { equipment_id: Number(equipmentId) } : {}),
      ...(status ? { status } : {}),
      ...(startDate && endDate ? { start_date: startDate, end_date: endDate } : {}),
    });
  }

  function resetFilters() {
    setCustomer('');
    setCustomerUserId('');
    setOrigin('');
    setEquipmentId('');
    setStatus('');
    setStartDate('');
    setEndDate('');
    feedback.clear();
    setFilters({});
  }

  return <>
    <PageHeader title="Reservas" description="Consulta el historial y organiza los alquileres por días completos." action={<Link className="button" to="/admin/reservas/nueva">Nueva reserva</Link>} />
    <form className="panel filters" onSubmit={applyFilters} noValidate aria-label="Filtros de reservas">
      {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
      <div className="form-grid">
        <Field name="customer" label="Cliente" hint="Busca por nombre o correo de la reserva."><input id="customer" name="customer" maxLength={254} value={customer} onChange={(event) => setCustomer(event.target.value)} /></Field>
        <Field name="customer_user_id" label="ID de cuenta" hint="Opcional. Filtra por propietario de cuenta, sin asociar históricos por correo." error={feedback.errors.customer_user_id}><input id="customer_user_id" name="customer_user_id" inputMode="numeric" value={customerUserId} onChange={(event) => setCustomerUserId(event.target.value)} /></Field>
        <Field name="equipment_id" label="Equipo">
          <select id="equipment_id" name="equipment_id" value={equipmentId} onChange={(event) => { setEquipmentId(event.target.value); }} disabled={equipment.loading}>
            <option value="">Todos los equipos</option>
            {equipment.data?.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}{item.active ? '' : ' (inactivo)'}</option>)}
          </select>
        </Field>
        <Field name="origin" label="Origen"><select id="origin" name="origin" value={origin} onChange={(event) => setOrigin(event.target.value as ReservationOrigin | '')}><option value="">Todos los orígenes</option>{Object.entries(reservationOrigins).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field name="status" label="Estado">
          <select id="status" name="status" value={status} onChange={(event) => { setStatus(event.target.value as ReservationStatus | ''); }}>
            <option value="">Todos los estados</option>
            <option value="confirmed">Confirmada</option>
            <option value="cancelled">Cancelada</option>
          </select>
        </Field>
        <Field name="start_date" label="Desde" error={feedback.errors.start_date}>
          <input id="start_date" name="start_date" type="date" value={startDate} onChange={(event) => { setStartDate(event.target.value); }} />
        </Field>
        <Field name="end_date" label="Hasta" error={feedback.errors.end_date}>
          <input id="end_date" name="end_date" type="date" value={endDate} onChange={(event) => { setEndDate(event.target.value); }} />
        </Field>
      </div>
      <p className="text-muted">Las fechas seleccionan reservas que solapan el intervalo; el día final queda excluido.</p>
      <div className="form-actions">
        <button className="button button-secondary" type="submit">Aplicar filtros</button>
        <button className="button button-secondary" type="button" onClick={resetFilters}>Limpiar filtros</button>
      </div>
    </form>
    {equipment.error && <Notice tone="error">{equipment.error} <button className="button button-secondary" type="button" onClick={equipment.reload}>Reintentar equipos</button></Notice>}
    {reservations.loading && <p role="status">Cargando reservas…</p>}
    {reservations.error && <Notice tone="error">{reservations.error} <button className="button button-secondary" type="button" onClick={reservations.reload}>Reintentar</button></Notice>}
    {!reservations.loading && !reservations.error && reservations.data && (reservations.data.length === 0
      ? <EmptyState title="No hay reservas con estos filtros" description="Prueba otro equipo o intervalo, o registra una nueva reserva." />
      : <section className="panel" aria-label="Listado de reservas">
        <div className="panel-header"><p className="text-muted">{reservations.data.length} reservas encontradas</p></div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table>
          <caption className="sr-only">Reservas y estado actual</caption>
          <thead><tr><th scope="col">Reserva / cliente</th><th scope="col">Propietario y origen</th><th scope="col">Equipo</th><th scope="col">Intervalo</th><th scope="col">Estado</th><th scope="col">Acción</th></tr></thead>
          <tbody>{reservations.data.map((reservation) => {
            const unit = equipment.data?.find((item) => item.id === reservation.equipment_id);
            return <tr key={reservation.id}>
              <td><span className="cell-title">#{reservation.id} · {reservation.customer_name}</span><span className="cell-subtitle">{reservation.customer_email}</span></td>
              <td><span className="cell-title">{reservationOwner(reservation)}</span><span className="cell-subtitle">{reservationOrigin(reservation)}</span></td>
              <td><Link to={`/admin/equipos/${reservation.equipment_id}`}>{unit?.code ?? `Equipo #${reservation.equipment_id}`}</Link><span className="cell-subtitle">{unit?.name}</span></td>
              <td><span className="cell-title">{formatDate(reservation.start_date)} → {formatDate(reservation.end_date)}</span><span className="cell-subtitle">Fin excluido</span></td>
              <td><StatusBadge kind={reservation.status} /></td>
              <td><Link to={`/admin/reservas/${reservation.id}`} aria-label={`Ver reserva #${reservation.id}`}>Ver detalle</Link></td>
            </tr>;
          })}</tbody>
        </table></div>
      </section>)}
  </>;
}
