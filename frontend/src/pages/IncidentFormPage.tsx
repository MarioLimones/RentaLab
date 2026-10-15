import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, type IncidentPriority } from '../api/client';
import { EmptyState, Field, Notice, PageHeader } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useIsMounted } from '../hooks/useIsMounted';
import { useResource } from '../hooks/useResource';

export default function IncidentFormPage() {
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const isMounted = useIsMounted();
  const [equipmentId, setEquipmentId] = useState(search.get('equipment_id') ?? '');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<IncidentPriority>('medium');
  const [blocking, setBlocking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const submitButton = useRef<HTMLButtonElement>(null);
  const load = useCallback(() => api.listEquipment(), []);
  const { data: equipment, loading, error, reload } = useResource(load);
  const feedback = useFormFeedback();

  useEffect(() => { if (confirming) confirmButton.current?.focus(); }, [confirming]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (feedback.pending) return;
    feedback.clear();
    const errors: Record<string, string> = {};
    if (!equipmentId) errors.equipment_id = 'Selecciona un equipo.';
    if (!title.trim()) errors.title = 'Escribe un título para la incidencia.';
    if (Object.keys(errors).length > 0) { feedback.setValidation(errors); return; }
    if (blocking) setConfirming(true);
    else void create();
  }

  async function create() {
    if (feedback.pending) return;
    feedback.clear();
    feedback.setPending(true);
    try {
      const incident = await api.createIncident({ equipment_id: Number(equipmentId), title, description, priority, blocking });
      if (!isMounted()) return;
      navigate(`/admin/incidencias/${incident.id}`, { state: { success: 'Incidencia registrada.' } });
    } catch (failure: unknown) {
      if (isMounted()) feedback.setFailure(failure);
    } finally {
      if (isMounted()) feedback.setPending(false);
    }
  }

  return <>
    <Link className="back-link" to="/admin/incidencias">Volver a incidencias</Link>
    <PageHeader title="Registrar incidencia" description="Registra una incidencia interna vinculada a una unidad física. Los avisos del cliente se crean desde su reserva." />
    {loading && <p role="status">Cargando equipos…</p>}
    {error && <Notice tone="error">{error} <button className="button button-secondary" type="button" onClick={reload}>Volver a cargar</button></Notice>}
    {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
    {equipment?.length === 0 ? <EmptyState title="Primero necesitas un equipo" description="Registra una unidad para poder asociarle incidencias."
      action={<Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link>} /> : equipment && <form className="panel stack" onSubmit={submit} noValidate aria-busy={feedback.pending}>
      <fieldset className="stack admin-incident-fields" disabled={feedback.pending || confirming}>
        <legend>Datos de la incidencia interna</legend>
      <div className="form-grid">
        <Field name="equipment_id" label="Equipo" error={feedback.errors.equipment_id} hint="También puedes registrar problemas de equipos inactivos."><select id="equipment_id" required value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)}>
          <option value="">Selecciona un equipo</option>{equipment.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}{item.active ? '' : ' (inactivo)'}</option>)}
        </select></Field>
        <Field name="priority" label="Prioridad" error={feedback.errors.priority}><select id="priority" value={priority} onChange={(event) => setPriority(event.target.value as IncidentPriority)}>
          <option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
        </select></Field>
      </div>
      <Field name="title" label="Título" error={feedback.errors.title}><input id="title" required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} /></Field>
      <Field name="description" label="Descripción" error={feedback.errors.description}><textarea id="description" maxLength={2000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></Field>
      <div className="checkbox-field"><input id="blocking" type="checkbox" checked={blocking} aria-invalid={Boolean(feedback.errors.blocking)} aria-describedby={feedback.errors.blocking ? 'blocking-hint blocking-error' : 'blocking-hint'} onChange={(event) => setBlocking(event.target.checked)} /><label htmlFor="blocking">Bloquea nuevas reservas</label></div>
      <p id="blocking-hint" className="text-muted">Una incidencia bloqueante sin resolver impide nuevas reservas. Las reservas existentes se conservan. La prioridad por sí sola no bloquea.</p>
      {feedback.errors.blocking && <p id="blocking-error" className="field-error">{feedback.errors.blocking}</p>}
      </fieldset>
      {confirming ? <fieldset className="stack confirmation"><legend>Confirmar bloqueo del equipo</legend><p>Se rechazarán nuevas reservas de este equipo hasta resolver o retirar el bloqueo. Las reservas confirmadas no se cancelan automáticamente.</p><div className="inline-actions"><button ref={confirmButton} className="button button-danger" type="button" disabled={feedback.pending} onClick={() => { void create(); }}>{feedback.pending ? 'Registrando…' : 'Sí, registrar y bloquear'}</button><button className="button button-secondary" type="button" disabled={feedback.pending} onClick={() => { setConfirming(false); queueMicrotask(() => submitButton.current?.focus()); }}>Volver a editar</button></div></fieldset> : <div className="form-actions"><button ref={submitButton} className="button" type="submit" disabled={feedback.pending}>{feedback.pending ? 'Registrando…' : 'Registrar incidencia'}</button><Link className="button button-secondary" to="/admin/incidencias">Cancelar</Link></div>}
    </form>}
  </>;
}
