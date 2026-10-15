import { useCallback, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, type Equipment } from '../api/client';
import { EmptyState, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useFormFeedback } from '../hooks/useFormFeedback';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';

function routeNotice(state: unknown): string | null {
  return typeof state === 'object' && state !== null && 'notice' in state && typeof state.notice === 'string' ? state.notice : null;
}

function EquipmentDetail({ equipmentId }: { equipmentId: number }) {
  const load = useCallback(async () => {
    const [equipment, reservations, incidents] = await Promise.all([
      api.getEquipment(equipmentId), api.listReservations({ equipment_id: equipmentId }), api.listIncidents({ equipment_id: equipmentId }),
    ]);
    return { equipment, reservations, incidents };
  }, [equipmentId]);
  const { data, loading, error, reload } = useResource(load);
  const [updated, setUpdated] = useState<{ source: Equipment; value: Equipment } | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const changing = useRef(false);
  const feedback = useFormFeedback();
  const location = useLocation();
  const notice = routeNotice(location.state);

  async function toggleActive(equipment: Equipment) {
    if (changing.current || loading || !data) return;
    changing.current = true;
    feedback.clear();
    setSuccess(null);
    feedback.setPending(true);
    try {
      const saved = await api.patchEquipment(equipment.id, { active: !equipment.active });
      setUpdated({ source: data.equipment, value: saved });
      setSuccess(`Equipo ${saved.active ? 'activado' : 'desactivado'} correctamente.`);
      reload();
    } catch (failure) {
      feedback.setFailure(failure);
    } finally {
      changing.current = false;
      feedback.setPending(false);
    }
  }

  if (loading && !data) return <p role="status">Cargando equipo y actividad…</p>;
  if (error && !data) return <><PageHeader title="Detalle del equipo" /><Notice tone="error">{error} <button type="button" className="button button-secondary" onClick={reload}>Volver a cargar</button></Notice><Link to="/admin/equipos">Volver a equipos</Link></>;
  if (!data) return null;
  const equipment = updated?.source === data.equipment ? updated.value : data.equipment;
  const blocking = data.incidents.filter((incident) => incident.blocking && incident.status !== 'resolved');

  return <>
    <Link className="back-link" to="/admin/equipos">← Volver a equipos</Link>
    <PageHeader title={equipment.name} description={`${equipment.code} · ${equipment.category}`} action={<div className="inline-actions"><button className="button button-secondary" type="button" disabled={loading || feedback.pending} onClick={reload}>Actualizar datos</button><Link className="button button-secondary" to={`/admin/equipos/${equipment.id}/editar`}>Editar equipo</Link></div>} />
    {loading && <p role="status">Actualizando equipo y actividad…</p>}
    {error && <Notice tone="error">{error} <button type="button" className="button button-secondary" onClick={reload}>Volver a cargar</button></Notice>}
    {(success ?? notice) && <Notice tone="success">{success ?? notice}</Notice>}
    {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
    {blocking.length > 0 && <Notice tone="warning">Este equipo tiene {blocking.length} {blocking.length === 1 ? 'incidencia bloqueante sin resolver' : 'incidencias bloqueantes sin resolver'}. Impiden nuevas reservas. El equipo también debe estar activo para admitirlas.</Notice>}
    <section className="panel" aria-labelledby="equipment-data-title">
      <div className="panel-header"><h2 id="equipment-data-title">Datos del equipo</h2><StatusBadge kind={equipment.active ? 'active' : 'inactive'} /></div>
      <dl className="detail-list"><div><dt>Código</dt><dd>{equipment.code}</dd></div><div><dt>Categoría</dt><dd>{equipment.category}</dd></div><div><dt>Descripción interna</dt><dd>{equipment.description || 'Sin descripción interna.'}</dd></div></dl>
      <div className="inline-actions"><button type="button" className="button button-secondary" disabled={feedback.pending || loading} onClick={() => { void toggleActive(equipment); }}>{feedback.pending ? 'Guardando…' : equipment.active ? 'Desactivar equipo' : 'Activar equipo'}</button><Link className="button" to={`/admin/reservas/nueva?equipment_id=${equipment.id}`}>Crear reserva</Link><Link className="button button-secondary" to={`/admin/incidencias/nueva?equipment_id=${equipment.id}`}>Registrar incidencia</Link></div>
      {!equipment.active && <p className="text-muted">El equipo inactivo conserva su historial y no admite nuevas reservas.</p>}
    </section>
    <section className="panel" aria-labelledby="equipment-public-title">
      <div className="panel-header"><h2 id="equipment-public-title">Ficha pública del catálogo</h2>{equipment.active && <Link to={`/equipos/${equipment.id}`}>Ver ficha pública</Link>}</div>
      <dl className="detail-list"><div><dt>Descripción pública</dt><dd>{equipment.public_description || 'Sin descripción pública.'}</dd></div><div><dt>Imagen</dt><dd>{equipment.image_url || 'Alternativa local de RentaLab.'}</dd></div></dl>
      <h3>Características técnicas</h3>
      {Object.keys(equipment.technical_specs ?? {}).length === 0 ? <p className="text-muted">Sin características técnicas.</p> : <dl className="detail-list">{Object.entries(equipment.technical_specs ?? {}).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
      {!equipment.active && <p className="text-muted">El equipo inactivo queda fuera del catálogo público.</p>}
      <Link to="/catalogo">Abrir catálogo de clientes</Link>
    </section>
    <div className="split-grid">
      <section className="panel" aria-labelledby="equipment-reservations-title"><div className="panel-header"><h2 id="equipment-reservations-title">Reservas del equipo</h2><span className="text-muted">{data.reservations.length} en total</span></div>
        {data.reservations.length === 0 ? <EmptyState title="Sin reservas" description="Las reservas de esta unidad aparecerán aquí, también las canceladas." /> : <ul className="detail-grid">{data.reservations.map((reservation) => <li key={reservation.id}><Link className="cell-title" to={`/admin/reservas/${reservation.id}`}>{reservation.customer_name} · #{reservation.id}</Link><p>{formatDate(reservation.start_date)} → {formatDate(reservation.end_date)} <span className="text-muted">(fin excluido)</span></p><StatusBadge kind={reservation.status} /></li>)}</ul>}
      </section>
      <section className="panel" aria-labelledby="equipment-incidents-title"><div className="panel-header"><h2 id="equipment-incidents-title">Incidencias del equipo</h2><span className="text-muted">{data.incidents.length} en total</span></div>
        {data.incidents.length === 0 ? <EmptyState title="Sin incidencias" description="No hay incidencias registradas para esta unidad." /> : <ul className="detail-grid">{data.incidents.map((incident) => <li key={incident.id}><Link className="cell-title" to={`/admin/incidencias/${incident.id}`}>{incident.title}</Link><div className="inline-actions"><StatusBadge kind={incident.status} /><StatusBadge kind={incident.priority} />{incident.blocking && <StatusBadge kind="blocking" />}</div></li>)}</ul>}
      </section>
    </div>
  </>;
}

export function EquipmentDetailPage() {
  const { id } = useParams();
  const equipmentId = Number(id);
  if (!Number.isSafeInteger(equipmentId) || equipmentId <= 0) return <><PageHeader title="Equipo no válido" /><Notice tone="error">El identificador del equipo no es válido.</Notice><Link to="/admin/equipos">Volver a equipos</Link></>;
  return <EquipmentDetail key={equipmentId} equipmentId={equipmentId} />;
}
