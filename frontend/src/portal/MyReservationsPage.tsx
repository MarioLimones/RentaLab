import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { EmptyState, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { formatDate } from '../lib/dates';
import './account.css';

export default function MyReservationsPage() {
  const resource = useResource(useCallback(async () => {
    const reservations = await api.listMyReservations();
    const equipmentIds = [...new Set(reservations.map((reservation) => reservation.equipment_id))];
    const equipmentNames = new Map(await Promise.all(equipmentIds.map(async (equipmentId): Promise<[number, string]> => {
      try {
        const equipment = await api.getPublicEquipment(equipmentId);
        return [equipmentId, equipment.name];
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return [equipmentId, `Equipo #${equipmentId} (ficha no disponible)`];
        throw error;
      }
    })));
    return { reservations, equipmentNames };
  }, []));
  const data = resource.data;

  return <div className="portal-account">
    <PageHeader title="Mis reservas" description="Consulta tus equipos, las fechas de alquiler y el historial de tus reservas." action={<Link className="button" to="/catalogo">Buscar un equipo</Link>} />
    {resource.loading && <p role="status">Cargando tus reservas…</p>}
    {resource.error && <Notice tone="error">{resource.error} <button className="button button-secondary" type="button" onClick={resource.reload}>Reintentar</button></Notice>}
    {data && !resource.loading && (data.reservations.length === 0
      ? <EmptyState title="Todavía no tienes reservas" description="Elige un equipo y unas fechas en el catálogo para preparar tu primer alquiler." action={<Link className="button" to="/catalogo">Explorar el catálogo</Link>} />
      : <ul className="portal-account-reservations" aria-label="Tus reservas">
        {data.reservations.map((reservation) => <li key={reservation.id}>
          <article className="portal-account-reservation">
            <div className="portal-account-reservation-heading">
              <p className="portal-account-reference">Reserva #{reservation.id}</p>
              <StatusBadge kind={reservation.status} />
            </div>
            <h2><Link to={`/mis-reservas/${reservation.id}`}>{data.equipmentNames.get(reservation.equipment_id)}</Link></h2>
            <p className="portal-account-date-range"><time dateTime={reservation.start_date}>{formatDate(reservation.start_date)}</time> a <time dateTime={reservation.end_date}>{formatDate(reservation.end_date)}</time></p>
            <p className="portal-account-muted">Inicio incluido · Fin excluido</p>
            <Link className="button button-secondary" to={`/mis-reservas/${reservation.id}`} aria-label={`Ver reserva #${reservation.id}`}>Ver reserva</Link>
          </article>
        </li>)}
      </ul>)}
  </div>;
}
