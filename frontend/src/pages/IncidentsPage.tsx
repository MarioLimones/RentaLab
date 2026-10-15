import { useCallback, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, type IncidentFilters, type IncidentPriority, type IncidentStatus } from '../api/client';
import { EmptyState, Field, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useResource } from '../hooks/useResource';

export default function IncidentsPage() {
  const [equipmentId, setEquipmentId] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [blocking, setBlocking] = useState('');
  const [filters, setFilters] = useState<IncidentFilters>({});
  const load = useCallback(async () => {
    const [incidents, equipment] = await Promise.all([api.listIncidents(filters), api.listEquipment()]);
    return { incidents, equipment };
  }, [filters]);
  const { data, loading, error, reload } = useResource(load);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      ...(equipmentId ? { equipment_id: Number(equipmentId) } : {}),
      ...(status ? { status: status as IncidentStatus } : {}),
      ...(priority ? { priority: priority as IncidentPriority } : {}),
      ...(blocking ? { blocking: blocking === 'true' } : {}),
    });
  }

  function clearFilters() {
    setEquipmentId(''); setStatus(''); setPriority(''); setBlocking(''); setFilters({});
  }

  return <>
    <PageHeader title="Incidencias" description="Avisos del cliente e incidencias internas. El bloqueo se decide desde administración."
      action={<Link className="button" to="/admin/incidencias/nueva">Registrar incidencia</Link>} />
    <form className="panel filters" onSubmit={applyFilters} aria-label="Filtros de incidencias">
      <Field name="incident-equipment-filter" label="Equipo"><select id="incident-equipment-filter" value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)}>
        <option value="">Todos los equipos</option>
        {data?.equipment.map((equipment) => <option key={equipment.id} value={equipment.id}>{equipment.code} · {equipment.name}</option>)}
      </select></Field>
      <Field name="incident-status-filter" label="Estado"><select id="incident-status-filter" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">Todos los estados</option><option value="open">Abierta</option><option value="in_progress">En curso</option><option value="resolved">Resuelta</option>
      </select></Field>
      <Field name="incident-priority-filter" label="Prioridad"><select id="incident-priority-filter" value={priority} onChange={(event) => setPriority(event.target.value)}>
        <option value="">Todas las prioridades</option><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
      </select></Field>
      <Field name="incident-blocking-filter" label="Bloqueo"><select id="incident-blocking-filter" value={blocking} onChange={(event) => setBlocking(event.target.value)}>
        <option value="">Todas las incidencias</option><option value="true">Bloqueantes</option><option value="false">No bloqueantes</option>
      </select></Field>
      <div className="inline-actions"><button className="button" type="submit" disabled={loading}>Aplicar filtros</button><button className="button button-secondary" type="button" onClick={clearFilters}>Limpiar filtros</button></div>
    </form>
    {error && <Notice tone="error">{error} <button className="button button-secondary" type="button" onClick={reload}>Volver a cargar</button></Notice>}
    {loading && <p role="status">Cargando incidencias…</p>}
    {data && !loading && !error && <section className="panel" aria-label="Listado de incidencias">
      <div className="panel-header"><h2>Incidencias registradas</h2><div className="inline-actions"><p className="text-muted">{data.incidents.length} resultados</p><button className="button button-secondary" type="button" disabled={loading} onClick={reload}>Actualizar listado</button></div></div>
      {data.incidents.length === 0 ? <EmptyState title="No hay incidencias con estos filtros" description="Puedes cambiar los filtros o registrar una nueva incidencia." /> : <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table>
        <caption className="sr-only">Incidencias y estado de cada equipo</caption>
        <thead><tr><th scope="col">Incidencia</th><th scope="col">Origen y autor</th><th scope="col">Equipo</th><th scope="col">Prioridad</th><th scope="col">Estado</th><th scope="col">Bloqueo</th></tr></thead>
        <tbody>{data.incidents.map((incident) => {
          const equipment = data.equipment.find((item) => item.id === incident.equipment_id);
          return <tr key={incident.id}>
            <td><Link className="cell-title" to={`/admin/incidencias/${incident.id}`}>{incident.title}</Link><span className="cell-subtitle">#{incident.id}</span></td>
            <td>{incident.reservation_id != null ? <><span>Aviso de cliente</span><Link className="cell-subtitle" to={`/admin/reservas/${incident.reservation_id}`}>Reserva #{incident.reservation_id}</Link></> : <span>Interna o histórica sin reserva vinculada</span>}<span className="cell-subtitle">{incident.author_user_id != null ? `Usuario #${incident.author_user_id}` : 'Sin autor de cuenta registrado'}</span></td>
            <td><Link to={`/admin/equipos/${incident.equipment_id}`}>{equipment?.code ?? `Equipo #${incident.equipment_id}`}</Link></td>
            <td><StatusBadge kind={incident.priority} /></td><td><StatusBadge kind={incident.status} /></td>
            <td>{incident.blocking ? (incident.status === 'resolved' ? 'Bloqueo resuelto' : 'Bloquea reservas') : 'No bloqueante'}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    </section>}
  </>;
}
