import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/cliente';
import { EstadoVacio, Aviso, CabeceraPagina } from '../componentes/interfaz';
import { useRecurso } from '../hooks/useRecurso';
import './cuenta.css';

const etiquetasEstado = { open: 'Pendiente de gestión', in_progress: 'En revisión', resolved: 'Resuelta' };

export default function PaginaMisIncidencias() {
  const recurso = useRecurso(useCallback(() => api.listarMisIncidencias(), []));
  return <div className="portal-account">
    <CabeceraPagina titulo="Mis incidencias" descripcion="Consulta los avisos que has enviado y las respuestas del equipo de RentaLab." />
    {recurso.cargando && <p role="status">Cargando tus incidencias…</p>}
    {recurso.error && <Aviso tono="error">{recurso.error} <button className="button button-secondary" type="button" onClick={recurso.recargar}>Reintentar</button></Aviso>}
    {recurso.datos && !recurso.cargando && (recurso.datos.length === 0
      ? <EstadoVacio titulo="No has enviado ningún aviso" descripcion="Si tienes un problema con un equipo, abre su reserva e informa desde allí." accion={<Link className="button button-secondary" to="/mis-reservas">Ver mis reservas</Link>} />
      : <ul className="portal-account-incidents" aria-label="Tus incidencias">{recurso.datos.map((incidencia) => <li key={incidencia.id}><article className="portal-account-panel">
        <div className="portal-account-panel-heading"><p className="portal-account-reference">Aviso #{incidencia.id} · <Link to={`/mis-reservas/${incidencia.reservation_id}`}>Reserva #{incidencia.reservation_id}</Link></p><span className={`badge badge-${incidencia.status}`}>{etiquetasEstado[incidencia.status]}</span></div>
        <h2>{incidencia.title}</h2>
        <p className="portal-account-user-text">{incidencia.description}</p>
        <section className="portal-account-response" aria-label={`Respuesta al aviso #${incidencia.id}`}><h3>Respuesta de RentaLab</h3><p className="portal-account-user-text">{incidencia.public_response || 'Pendiente de respuesta.'}</p></section>
      </article></li>)}</ul>)}
  </div>;
}
