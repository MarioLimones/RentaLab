import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, type Incident, type IncidentUpdate, type IncidentPriority, type IncidentStatusChange } from '../api/client';
import { Field, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useResource } from '../hooks/useResource';
import '../admin/incidents.css';

function creationMessage(state: unknown): string | null {
  if (typeof state === 'object' && state !== null && 'success' in state && typeof state.success === 'string') return state.success;
  return null;
}

function ManagementForm({ incident, busy, errors, onSave }: {
  incident: Incident;
  busy: boolean;
  errors: Record<string, string>;
  onSave: (change: IncidentUpdate) => Promise<boolean>;
}) {
  const [priority, setPriority] = useState<IncidentPriority>(incident.priority);
  const [blocking, setBlocking] = useState(incident.blocking);
  const [internalNotes, setInternalNotes] = useState(incident.internal_notes ?? '');
  const [publicResponse, setPublicResponse] = useState(incident.public_response ?? '');
  const [confirming, setConfirming] = useState(false);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const saveButton = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (confirming) confirmButton.current?.focus(); }, [confirming]);

  async function save() {
    if (busy) return;
    const saved = await onSave({ priority, blocking, internal_notes: internalNotes, public_response: publicResponse });
    if (saved) setConfirming(false);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (blocking && !incident.blocking && incident.status !== 'resolved') setConfirming(true);
    else void save();
  }

  return <section className="panel stack" aria-label="Prioridad, bloqueo y comunicación">
    <h2>Prioridad, bloqueo y comunicación</h2>
    <form className="stack" onSubmit={submit} noValidate aria-busy={busy}>
      <Field name="priority" label="Prioridad" error={errors.priority}><select id="priority" value={priority} disabled={busy || confirming} onChange={(event) => setPriority(event.target.value as IncidentPriority)}>
        <option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
      </select></Field>
      <div className="checkbox-field"><input id="blocking" type="checkbox" checked={blocking} disabled={busy || confirming} aria-invalid={Boolean(errors.blocking)} aria-describedby={errors.blocking ? 'blocking-hint blocking-error' : 'blocking-hint'} onChange={(event) => setBlocking(event.target.checked)} /><label htmlFor="blocking">Bloquea nuevas reservas</label></div>
      <p id="blocking-hint" className="text-muted">La prioridad por sí sola no bloquea. Solo las incidencias bloqueantes sin resolver impiden nuevas reservas.</p>
      {errors.blocking && <p id="blocking-error" className="field-error">{errors.blocking}</p>}
      <Field name="internal_notes" label="Notas internas" error={errors.internal_notes} hint="Solo administración. No se muestran al cliente; hasta 2000 caracteres."><textarea id="internal_notes" rows={4} maxLength={2000} disabled={busy || confirming} value={internalNotes} onChange={(event) => setInternalNotes(event.target.value)} /></Field>
      <Field name="public_response" label="Respuesta visible al cliente" error={errors.public_response} hint={incident.reservation_id != null ? 'El cliente verá este texto en sus avisos; hasta 2000 caracteres.' : 'Esta incidencia no tiene una reserva vinculada. Guardar una respuesta no la asigna a ningún cliente.'}><textarea id="public_response" rows={4} maxLength={2000} disabled={busy || confirming} value={publicResponse} onChange={(event) => setPublicResponse(event.target.value)} /></Field>
      {confirming ? <fieldset className="stack confirmation">
        <legend>Confirmar bloqueo del equipo</legend>
        <p>Se rechazarán nuevas reservas de este equipo hasta resolver o retirar el bloqueo. Las reservas confirmadas se conservan y no se cancelan automáticamente.</p>
        <div className="inline-actions">
          <button ref={confirmButton} className="button button-danger" type="button" disabled={busy} onClick={() => { void save(); }}>{busy ? 'Guardando…' : 'Sí, guardar y bloquear'}</button>
          <button className="button button-secondary" type="button" disabled={busy} onClick={() => { setConfirming(false); queueMicrotask(() => saveButton.current?.focus()); }}>Volver a editar</button>
        </div>
      </fieldset> : <div className="form-actions"><button ref={saveButton} className="button" type="submit" disabled={busy}>{busy ? 'Guardando…' : 'Guardar gestión'}</button></div>}
    </form>
  </section>;
}

function IncidentDetail({ id }: { id: string | undefined }) {
  const location = useLocation();
  const [resolution, setResolution] = useState('');
  const [success, setSuccess] = useState<string | null>(() => creationMessage(location.state));
  const feedback = useFormFeedback();
  const load = useCallback(async () => {
    const incidentId = Number(id);
    if (!Number.isSafeInteger(incidentId) || incidentId <= 0) throw new Error('El identificador de la incidencia no es válido.');
    const [incident, equipment] = await Promise.all([api.getIncident(incidentId), api.listEquipment()]);
    return { incident, equipment: equipment.find((item) => item.id === incident.equipment_id) };
  }, [id]);
  const { data, loading, error, reload } = useResource(load);
  const [persisted, setPersisted] = useState<{ incident: Incident; source: typeof data; action: 'status' | 'management' } | null>(null);
  // Keep a successful write authoritative if its follow-up GET fails. A new GET
  // replaces the snapshot, including the calculated warning and reservations.
  const incident = persisted && persisted.source === data ? persisted.incident : data?.incident;
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const resolutionInput = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!persisted) return;
    if (persisted.action === 'management' || persisted.incident.status === 'resolved') detailHeading.current?.focus();
    else resolutionInput.current?.focus();
  }, [persisted]);

  async function saveManagement(change: IncidentUpdate): Promise<boolean> {
    if (!data || !incident || feedback.pending) return false;
    feedback.clear(); setSuccess(null); feedback.setPending(true);
    try {
      const saved = await api.patchIncident(incident.id, change);
      setPersisted({ incident: saved, source: data, action: 'management' });
      setSuccess('Gestión de la incidencia guardada.');
      reload();
      return true;
    } catch (failure: unknown) {
      feedback.setFailure(failure);
      return false;
    } finally {
      feedback.setPending(false);
    }
  }

  async function changeStatus(change: IncidentStatusChange) {
    if (!data || !incident || feedback.pending) return;
    feedback.clear(); setSuccess(null); feedback.setPending(true);
    try {
      const saved = await api.changeIncidentStatus(incident.id, change);
      setPersisted({ incident: saved, source: data, action: 'status' });
      setSuccess(change.status === 'resolved' ? 'Incidencia resuelta. Se conserva su historial.' : 'La incidencia está en curso.');
      reload();
    } catch (failure: unknown) {
      feedback.setFailure(failure);
    } finally {
      feedback.setPending(false);
    }
  }

  function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    feedback.clear();
    if (!resolution.trim()) {
      feedback.setValidation({ resolution: 'Explica cómo se ha resuelto la incidencia.' });
      return;
    }
    void changeStatus({ status: 'resolved', resolution: resolution.trim() });
  }

  return <>
    <Link className="back-link" to="/admin/incidencias">Volver a incidencias</Link>
    {loading && <p role="status">Cargando incidencia…</p>}
    {error && <Notice tone="error">{error} <button className="button button-secondary" type="button" onClick={reload}>Volver a cargar</button></Notice>}
    {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
    {success && <Notice tone="success">{success}</Notice>}
    {data && incident && <>
      <PageHeader title={incident.title} description={`Incidencia #${incident.id}`} />
      <section className="panel stack admin-incident-detail" aria-label="Detalle de incidencia">
        <div className="panel-header"><h2 ref={detailHeading} tabIndex={-1}>Datos de la incidencia</h2><div className="inline-actions"><StatusBadge kind={incident.status} /><StatusBadge kind={incident.priority} /></div></div>
        <dl className="detail-list">
          <div><dt>Equipo</dt><dd><Link to={`/admin/equipos/${incident.equipment_id}`}>{data.equipment ? `${data.equipment.code} · ${data.equipment.name}` : `Equipo #${incident.equipment_id}`}</Link></dd></div>
          <div><dt>Origen</dt><dd>{incident.reservation_id != null ? 'Aviso de cliente' : 'Interna o histórica sin reserva vinculada'}</dd></div>
          <div><dt>Reserva vinculada</dt><dd>{incident.reservation_id != null ? <Link to={`/admin/reservas/${incident.reservation_id}`}>Reserva #{incident.reservation_id}</Link> : 'Sin reserva vinculada'}</dd></div>
          <div><dt>Autor</dt><dd>{incident.author_user_id != null ? `Usuario #${incident.author_user_id}` : 'Sin autor de cuenta registrado'}</dd></div>
          <div><dt>Descripción</dt><dd>{incident.description || 'Sin descripción.'}</dd></div>
          <div><dt>Bloqueo</dt><dd>{incident.blocking ? (incident.status === 'resolved' ? 'Incidencia bloqueante resuelta.' : 'Impide nuevas reservas de este equipo.') : 'No impide nuevas reservas.'}</dd></div>
        </dl>
        {incident.warning && <Notice tone="warning">{incident.warning}</Notice>}
        {incident.confirmed_reservation_ids.length > 0 && <div><h2>Reservas confirmadas del equipo</h2><p className="text-muted">Reservas actualmente confirmadas de esta unidad, sin filtro de fechas. El bloqueo no las modifica.</p><ul>{incident.confirmed_reservation_ids.map((reservationId) => <li key={reservationId}><Link to={`/admin/reservas/${reservationId}`}>Reserva #{reservationId}</Link></li>)}</ul></div>}
        {incident.status === 'resolved' && <div><h2>Resolución interna</h2><p className="admin-incident-text">{incident.resolution}</p><p className="text-muted">La disponibilidad también depende de otras incidencias, del estado activo y del intervalo de reserva.</p></div>}
      </section>
      <ManagementForm key={JSON.stringify([incident.priority, incident.blocking, incident.internal_notes, incident.public_response])} incident={incident} busy={feedback.pending || loading} errors={feedback.errors} onSave={saveManagement} />
      {incident.status !== 'resolved' && <section className="panel stack" aria-label="Gestionar estado de incidencia">
        <h2>Estado y resolución interna</h2>
        {incident.status === 'open' && <div><button className="button button-secondary" type="button" disabled={feedback.pending || loading} onClick={() => { void changeStatus({ status: 'in_progress' }); }}>Iniciar trabajo</button></div>}
        <form className="stack" onSubmit={resolve} noValidate aria-busy={feedback.pending}>
          <Field name="resolution" label="Resolución" error={feedback.errors.resolution} hint="Obligatoria para cerrar. Es interna y no se copia a la respuesta visible al cliente."><textarea ref={resolutionInput} id="resolution" required maxLength={2000} rows={4} disabled={feedback.pending || loading} value={resolution} onChange={(event) => setResolution(event.target.value)} /></Field>
          <p className="text-muted">Resolver retira este bloqueo. El equipo solo admitirá nuevas reservas si sigue activo, no quedan otros bloqueos y el intervalo está libre.</p>
          <div className="form-actions"><button className="button" type="submit" disabled={feedback.pending || loading}>{feedback.pending ? 'Guardando…' : 'Resolver incidencia'}</button></div>
        </form>
      </section>}
    </>}
  </>;
}

export default function IncidentDetailPage() {
  const { id } = useParams();
  return <IncidentDetail key={id} id={id} />;
}
