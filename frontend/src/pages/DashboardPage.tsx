import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';
import { todayInMadrid } from '../portal/dateRange';
import AvailabilitySummary from '../admin/AvailabilitySummary';

export function DashboardPage() {
  const load = useCallback(async () => {
    const [equipment, reservations, incidents] = await Promise.all([api.listEquipment(), api.listReservations(), api.listIncidents()]);
    return { equipment, reservations, incidents };
  }, []);
  const { data, loading, error, reload } = useResource(load);
  const today = todayInMadrid();
  const confirmed = data?.reservations.filter((reservation) => reservation.status === 'confirmed') ?? [];
  const upcoming = confirmed.filter((reservation) => reservation.end_date > today).sort((left, right) => left.start_date.localeCompare(right.start_date) || left.id - right.id).slice(0, 6);
  const unresolved = data?.incidents.filter((incident) => incident.status !== 'resolved') ?? [];
  const blocking = unresolved.filter((incident) => incident.blocking);
  const blockedIds = [...new Set(blocking.map((incident) => incident.equipment_id))];
  const equipmentById = new Map(data?.equipment.map((equipment) => [equipment.id, equipment]));

  return <>
    <PageHeader title="Resumen" description="Una vista de la actividad real de RentaLab. Datos ficticios para aprender y demostrar el producto." action={<Link className="button" to="/admin/reservas/nueva">Crear reserva</Link>} />
    {loading && <p role="status">Cargando resumen…</p>}
    {error && <Notice tone="error">{error} <button type="button" className="button button-secondary" onClick={reload}>Volver a cargar</button></Notice>}
    {!loading && !error && data && <>
      <p className="text-muted">Actividad acumulada de todas las fechas. Próximas reservas según la fecha de Madrid.</p>
      <div className="stat-grid" aria-label="Cifras del negocio">
        <article className="stat"><span>Equipos en catálogo</span><strong>{data.equipment.length}</strong><Link to="/admin/equipos">Ver catálogo →</Link></article>
        <article className="stat"><span>Equipos activos</span><strong>{data.equipment.filter((equipment) => equipment.active).length}</strong><span className="text-muted">Su disponibilidad depende del rango.</span></article>
        <article className="stat"><span>Reservas confirmadas</span><strong>{confirmed.length}</strong><Link to="/admin/reservas">Ver reservas →</Link></article>
        <article className="stat"><span>Incidencias sin resolver</span><strong>{unresolved.length}</strong><Link to="/admin/incidencias">Ver incidencias →</Link></article>
      </div>
      <AvailabilitySummary equipment={data.equipment} />
      {data.equipment.length === 0 && <section className="panel"><EmptyState title="Empieza por tu catálogo" description="Registra una unidad física para crear reservas e incidencias." action={<Link className="button" to="/admin/equipos/nuevo">Crear primer equipo</Link>} /></section>}
      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="upcoming-title"><div className="panel-header"><div><h2 id="upcoming-title">Próximas reservas</h2><p className="text-muted">En curso o pendientes de finalizar desde el {formatDate(today)}. Hasta seis reservas.</p></div><Link to="/admin/reservas">Ver todas</Link></div>
          {upcoming.length === 0 ? <EmptyState title="No hay próximas reservas" description="Aquí aparecerán las reservas confirmadas que aún no hayan terminado." /> : <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table><caption className="sr-only">Próximas reservas confirmadas</caption><thead><tr><th scope="col">Cliente y equipo</th><th scope="col">Periodo</th><th scope="col">Estado</th></tr></thead><tbody>{upcoming.map((reservation) => <tr key={reservation.id}><td><Link className="cell-title" to={`/admin/reservas/${reservation.id}`}>{reservation.customer_name} · #{reservation.id}</Link><span className="cell-subtitle">{equipmentById.get(reservation.equipment_id)?.name ?? `Equipo #${reservation.equipment_id}`}</span></td><td>{formatDate(reservation.start_date)} → {formatDate(reservation.end_date)}<span className="cell-subtitle">Fin excluido</span></td><td><StatusBadge kind={reservation.status} /></td></tr>)}</tbody></table></div>}
        </section>
        <section className="panel" aria-labelledby="blocking-title"><div className="panel-header"><div><h2 id="blocking-title">Equipos con incidencias bloqueantes</h2><p className="text-muted">{blockedIds.length} {blockedIds.length === 1 ? 'equipo requiere' : 'equipos requieren'} atención antes de nuevas reservas.</p></div></div>
          {blocking.length === 0 ? <EmptyState title="Sin incidencias bloqueantes" description="No hay averías sin resolver que bloqueen nuevas reservas. Las fechas y el estado activo se comprueban al reservar." /> : <ul className="detail-grid">{blockedIds.map((equipmentId) => <li key={equipmentId}><Link className="cell-title" to={`/admin/equipos/${equipmentId}`}>{equipmentById.get(equipmentId)?.name ?? `Equipo #${equipmentId}`}</Link>{blocking.filter((incident) => incident.equipment_id === equipmentId).map((incident) => <div className="stack" key={incident.id}><Link to={`/admin/incidencias/${incident.id}`}>{incident.title}</Link><div className="inline-actions"><StatusBadge kind={incident.status} /><StatusBadge kind={incident.priority} /></div></div>)}</li>)}</ul>}
        </section>
      </div>
    </>}
  </>;
}
