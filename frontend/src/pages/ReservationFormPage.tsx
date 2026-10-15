import { useCallback, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Availability } from '../api/client';
import { EmptyState, Field, Notice, PageHeader } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useIsMounted } from '../hooks/useIsMounted';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';

const availabilityMessages: Record<NonNullable<Availability['reason']>, string> = {
  equipment_inactive: 'El equipo está inactivo.',
  blocking_incident: 'El equipo tiene una incidencia bloqueante sin resolver.',
  reservation_overlap: 'El equipo tiene una reserva confirmada que solapa este intervalo.',
};

export default function ReservationFormPage() {
  const navigate = useNavigate();
  const isMounted = useIsMounted();
  const [search] = useSearchParams();
  const initialEquipment = search.get('equipment_id') ?? '';
  const [equipmentId, setEquipmentId] = useState(/^\d+$/.test(initialEquipment) ? initialEquipment : '');
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [externalReference, setExternalReference] = useState('');
  const equipment = useResource(useCallback(() => api.listEquipment(), []));
  const feedback = useFormFeedback();
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [checking, setChecking] = useState(false);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);
  const availabilityRequest = useRef(0);

  function invalidateAvailability() {
    availabilityRequest.current += 1;
    setAvailability(null);
    setAvailabilityError(null);
    setChecking(false);
  }

  function rangeErrors(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!equipmentId) errors.equipment_id = 'Selecciona un equipo.';
    if (!startDate) errors.start_date = 'Indica la fecha de inicio.';
    if (!endDate) errors.end_date = 'Indica la fecha de fin.';
    if (startDate && endDate && endDate <= startDate) errors.end_date = 'La fecha de fin debe ser posterior al inicio.';
    return errors;
  }

  async function checkAvailability() {
    feedback.clear();
    const errors = rangeErrors();
    if (Object.keys(errors).length > 0) {
      feedback.setValidation(errors);
      return;
    }
    const requestId = ++availabilityRequest.current;
    setChecking(true);
    setAvailability(null);
    setAvailabilityError(null);
    try {
      const result = await api.getEquipmentAvailability(Number(equipmentId), { start_date: startDate, end_date: endDate });
      if (isMounted() && requestId === availabilityRequest.current) setAvailability(result);
    } catch (error) {
      if (isMounted() && requestId === availabilityRequest.current) {
        setAvailabilityError(error instanceof Error ? error.message : 'No se pudo consultar la disponibilidad. Vuelve a intentarlo.');
      }
    } finally {
      if (isMounted() && requestId === availabilityRequest.current) setChecking(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    feedback.clear();
    const errors = rangeErrors();
    if (!customerName.trim()) errors.customer_name = 'Indica el nombre del cliente.';
    if (!customerEmail.trim()) errors.customer_email = 'Indica el correo del cliente.';
    else if (!event.currentTarget.querySelector<HTMLInputElement>('#customer_email')?.validity.valid) {
      errors.customer_email = 'Introduce un correo válido, por ejemplo cliente@example.test.';
    }
    if (Object.keys(errors).length > 0) {
      feedback.setValidation(errors);
      return;
    }
    feedback.setPending(true);
    try {
      const result = await api.createReservation({
        equipment_id: Number(equipmentId), customer_name: customerName, customer_email: customerEmail,
        start_date: startDate, end_date: endDate, external_reference: externalReference.trim() || null,
      });
      if (!isMounted()) return;
      navigate(`/admin/reservas/${result.id}`, { state: { created: true } });
    } catch (error) {
      if (isMounted()) feedback.setFailure(error);
    } finally {
      if (isMounted()) feedback.setPending(false);
    }
  }

  const selectedEquipment = equipment.data?.find((item) => item.id === Number(equipmentId));

  return <>
    <Link className="back-link" to="/admin/reservas">← Reservas</Link>
    <PageHeader title="Nueva reserva" description="Cada reserva corresponde a una unidad física. El servidor confirma el equipo y el intervalo al guardar." />
    {equipment.loading && <p role="status">Cargando equipos…</p>}
    {equipment.error && <Notice tone="error">{equipment.error} <button className="button button-secondary" type="button" onClick={equipment.reload}>Reintentar</button></Notice>}
    {equipment.data?.length === 0 && <EmptyState title="Todavía no hay equipos" description="Crea una unidad antes de registrar una reserva." action={<Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link>} />}
    {equipment.data && equipment.data.length > 0 && <form className="panel stack" onSubmit={(event) => { void submit(event); }} noValidate>
      {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
      <div className="form-grid">
        <Field name="equipment_id" label="Equipo" error={feedback.errors.equipment_id}>
          <select id="equipment_id" name="equipment_id" value={equipmentId} onChange={(event) => { setEquipmentId(event.target.value); invalidateAvailability(); }} required>
            <option value="">Selecciona un equipo</option>
            {equipment.data.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}{item.active ? '' : ' (inactivo)'}</option>)}
          </select>
        </Field>
        <Field name="external_reference" label="Referencia externa (opcional)" error={feedback.errors.external_reference} hint="La referencia es única y se conserva al cancelar.">
          <input id="external_reference" name="external_reference" value={externalReference} onChange={(event) => { setExternalReference(event.target.value); }} maxLength={120} />
        </Field>
        <Field name="customer_name" label="Nombre del cliente" error={feedback.errors.customer_name}>
          <input id="customer_name" name="customer_name" value={customerName} onChange={(event) => { setCustomerName(event.target.value); }} autoComplete="name" maxLength={120} required />
        </Field>
        <Field name="customer_email" label="Correo del cliente" error={feedback.errors.customer_email}>
          <input id="customer_email" name="customer_email" type="email" value={customerEmail} onChange={(event) => { setCustomerEmail(event.target.value); }} autoComplete="email" maxLength={254} required />
        </Field>
        <Field name="start_date" label="Fecha de inicio" error={feedback.errors.start_date} hint="El primer día de alquiler está incluido.">
          <input id="start_date" name="start_date" type="date" value={startDate} onChange={(event) => { setStartDate(event.target.value); invalidateAvailability(); }} required />
        </Field>
        <Field name="end_date" label="Fecha de fin" error={feedback.errors.end_date} hint="El día de devolución está excluido; otra reserva puede comenzar ese día.">
          <input id="end_date" name="end_date" type="date" value={endDate} onChange={(event) => { setEndDate(event.target.value); invalidateAvailability(); }} required />
        </Field>
      </div>
      <div className="stack">
        <div><button className="button button-secondary" type="button" onClick={() => { void checkAvailability(); }} disabled={checking || feedback.pending}>{checking ? 'Consultando…' : 'Consultar disponibilidad'}</button></div>
        <p className="text-muted">La consulta es orientativa: no retiene el equipo. La disponibilidad se comprueba de nuevo al crear.</p>
        {availabilityError && <Notice tone="error">{availabilityError}</Notice>}
        {availability && <section className="panel" aria-label="Resultado de disponibilidad" aria-live="polite">
          <p className="cell-title">{selectedEquipment?.code ?? `Equipo #${availability.equipment_id}`} · {selectedEquipment?.name}</p>
          <p>Del {formatDate(availability.start_date)} al {formatDate(availability.end_date)} (fin excluido).</p>
          <Notice tone={availability.available ? 'success' : 'warning'}>{availability.available ? 'Disponible para este intervalo.' : availability.reason ? availabilityMessages[availability.reason] : 'No disponible para este intervalo.'}</Notice>
        </section>}
      </div>
      <div className="form-actions">
        <button className="button" type="submit" disabled={feedback.pending}>{feedback.pending ? 'Creando…' : 'Crear reserva'}</button>
        <Link className="button button-secondary" to="/admin/reservas">Volver al listado</Link>
      </div>
    </form>}
  </>;
}
