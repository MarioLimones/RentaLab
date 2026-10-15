import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { EmptyState, Notice, PageHeader } from '../components/ui';
import { useResource } from '../hooks/useResource';
import './account.css';

const statusLabels = { open: 'Pendiente de gestión', in_progress: 'En revisión', resolved: 'Resuelta' };

export default function MyIncidentsPage() {
  const resource = useResource(useCallback(() => api.listMyIncidents(), []));
  return <div className="portal-account">
    <PageHeader title="Mis incidencias" description="Consulta los avisos que has enviado y las respuestas del equipo de RentaLab." />
    {resource.loading && <p role="status">Cargando tus incidencias…</p>}
    {resource.error && <Notice tone="error">{resource.error} <button className="button button-secondary" type="button" onClick={resource.reload}>Reintentar</button></Notice>}
    {resource.data && !resource.loading && (resource.data.length === 0
      ? <EmptyState title="No has enviado ningún aviso" description="Si tienes un problema con un equipo, abre su reserva e informa desde allí." action={<Link className="button button-secondary" to="/mis-reservas">Ver mis reservas</Link>} />
      : <ul className="portal-account-incidents" aria-label="Tus incidencias">{resource.data.map((incident) => <li key={incident.id}><article className="portal-account-panel">
        <div className="portal-account-panel-heading"><p className="portal-account-reference">Aviso #{incident.id} · <Link to={`/mis-reservas/${incident.reservation_id}`}>Reserva #{incident.reservation_id}</Link></p><span className={`badge badge-${incident.status}`}>{statusLabels[incident.status]}</span></div>
        <h2>{incident.title}</h2>
        <p className="portal-account-user-text">{incident.description}</p>
        <section className="portal-account-response" aria-label={`Respuesta al aviso #${incident.id}`}><h3>Respuesta de RentaLab</h3><p className="portal-account-user-text">{incident.public_response || 'Pendiente de respuesta.'}</p></section>
      </article></li>)}</ul>)}
  </div>;
}
