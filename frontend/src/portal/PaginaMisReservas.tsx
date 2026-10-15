import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, ErrorApi } from '../api/cliente';
import { EstadoVacio, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';
import './cuenta.css';

export default function PaginaMisReservas() {
  const recurso = useRecurso(useCallback(async () => {
    const reservas = await api.listarMisReservas();
    const idsEquipos = [...new Set(reservas.map((reserva) => reserva.equipment_id))];
    const nombresEquipos = new Map(await Promise.all(idsEquipos.map(async (idEquipo): Promise<[number, string]> => {
      try {
        const equipo = await api.obtenerEquipoPublico(idEquipo);
        return [idEquipo, equipo.name];
      } catch (error) {
        if (error instanceof ErrorApi && error.estado === 404) return [idEquipo, `Equipo #${idEquipo} (ficha no disponible)`];
        throw error;
      }
    })));
    return { reservas, nombresEquipos };
  }, []));
  const datos = recurso.datos;

  return <div className="portal-account">
    <CabeceraPagina titulo="Mis reservas" descripcion="Consulta tus equipos, las fechas de alquiler y el historial de tus reservas." accion={<Link className="button" to="/catalogo">Buscar un equipo</Link>} />
    {recurso.cargando && <p role="status">Cargando tus reservas…</p>}
    {recurso.error && <Aviso tono="error">{recurso.error} <button className="button button-secondary" type="button" onClick={recurso.recargar}>Reintentar</button></Aviso>}
    {datos && !recurso.cargando && (datos.reservas.length === 0
      ? <EstadoVacio titulo="Todavía no tienes reservas" descripcion="Elige un equipo y unas fechas en el catálogo para preparar tu primer alquiler." accion={<Link className="button" to="/catalogo">Explorar el catálogo</Link>} />
      : <ul className="portal-account-reservations" aria-label="Tus reservas">
        {datos.reservas.map((reserva) => <li key={reserva.id}>
          <article className="portal-account-reservation">
            <div className="portal-account-reservation-heading">
              <p className="portal-account-reference">Reserva #{reserva.id}</p>
              <EtiquetaEstado clase={reserva.status} />
            </div>
            <h2><Link to={`/mis-reservas/${reserva.id}`}>{datos.nombresEquipos.get(reserva.equipment_id)}</Link></h2>
            <p className="portal-account-date-range"><time dateTime={reserva.start_date}>{formatearFecha(reserva.start_date)}</time> a <time dateTime={reserva.end_date}>{formatearFecha(reserva.end_date)}</time></p>
            <p className="portal-account-muted">Inicio incluido · Fin excluido</p>
            <Link className="button button-secondary" to={`/mis-reservas/${reserva.id}`} aria-label={`Ver reserva #${reserva.id}`}>Ver reserva</Link>
          </article>
        </li>)}
      </ul>)}
  </div>;
}
