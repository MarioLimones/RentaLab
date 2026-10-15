import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/cliente';
import { EstadoVacio, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';
import { hoyEnMadrid } from '../portal/intervaloFechas';
import ResumenDisponibilidad from '../administracion/ResumenDisponibilidad';

export function PaginaResumen() {
  const cargar = useCallback(async () => {
    const [equipo, reservas, incidencias] = await Promise.all([api.listarEquipos(), api.listarReservas(), api.listarIncidencias()]);
    return { equipo, reservas, incidencias };
  }, []);
  const { datos, cargando, error, recargar } = useRecurso(cargar);
  const hoy = hoyEnMadrid();
  const confirmado = datos?.reservas.filter((reserva) => reserva.status === 'confirmed') ?? [];
  const proximos = confirmado.filter((reserva) => reserva.end_date > hoy).sort((izquierda, derecha) => izquierda.start_date.localeCompare(derecha.start_date) || izquierda.id - derecha.id).slice(0, 6);
  const sinResolver = datos?.incidencias.filter((incidencia) => incidencia.status !== 'resolved') ?? [];
  const bloqueante = sinResolver.filter((incidencia) => incidencia.blocking);
  const idsBloqueados = [...new Set(bloqueante.map((incidencia) => incidencia.equipment_id))];
  const equiposPorId = new Map(datos?.equipo.map((equipo) => [equipo.id, equipo]));

  return <>
    <CabeceraPagina titulo="Resumen" descripcion="Una vista de la actividad real de RentaLab. Datos ficticios para aprender y demostrar el producto." accion={<Link className="button" to="/admin/reservas/nueva">Crear reserva</Link>} />
    {cargando && <p role="status">Cargando resumen…</p>}
    {error && <Aviso tono="error">{error} <button type="button" className="button button-secondary" onClick={recargar}>Volver a cargar</button></Aviso>}
    {!cargando && !error && datos && <>
      <p className="text-muted">Actividad acumulada de todas las fechas. Próximas reservas según la fecha de Madrid.</p>
      <div className="stat-grid" aria-label="Cifras del negocio">
        <article className="stat"><span>Equipos en catálogo</span><strong>{datos.equipo.length}</strong><Link to="/admin/equipos">Ver catálogo →</Link></article>
        <article className="stat"><span>Equipos activos</span><strong>{datos.equipo.filter((equipo) => equipo.active).length}</strong><span className="text-muted">Su disponibilidad depende del rango.</span></article>
        <article className="stat"><span>Reservas confirmadas</span><strong>{confirmado.length}</strong><Link to="/admin/reservas">Ver reservas →</Link></article>
        <article className="stat"><span>Incidencias sin resolver</span><strong>{sinResolver.length}</strong><Link to="/admin/incidencias">Ver incidencias →</Link></article>
      </div>
      <ResumenDisponibilidad equipo={datos.equipo} />
      {datos.equipo.length === 0 && <section className="panel"><EstadoVacio titulo="Empieza por tu catálogo" descripcion="Registra una unidad física para crear reservas e incidencias." accion={<Link className="button" to="/admin/equipos/nuevo">Crear primer equipo</Link>} /></section>}
      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="upcoming-title"><div className="panel-header"><div><h2 id="upcoming-title">Próximas reservas</h2><p className="text-muted">En curso o pendientes de finalizar desde el {formatearFecha(hoy)}. Hasta seis reservas.</p></div><Link to="/admin/reservas">Ver todas</Link></div>
          {proximos.length === 0 ? <EstadoVacio titulo="No hay próximas reservas" descripcion="Aquí aparecerán las reservas confirmadas que aún no hayan terminado." /> : <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table><caption className="sr-only">Próximas reservas confirmadas</caption><thead><tr><th scope="col">Cliente y equipo</th><th scope="col">Periodo</th><th scope="col">Estado</th></tr></thead><tbody>{proximos.map((reserva) => <tr key={reserva.id}><td><Link className="cell-title" to={`/admin/reservas/${reserva.id}`}>{reserva.customer_name} · #{reserva.id}</Link><span className="cell-subtitle">{equiposPorId.get(reserva.equipment_id)?.name ?? `Equipo #${reserva.equipment_id}`}</span></td><td>{formatearFecha(reserva.start_date)} → {formatearFecha(reserva.end_date)}<span className="cell-subtitle">Fin excluido</span></td><td><EtiquetaEstado clase={reserva.status} /></td></tr>)}</tbody></table></div>}
        </section>
        <section className="panel" aria-labelledby="blocking-title"><div className="panel-header"><div><h2 id="blocking-title">Equipos con incidencias bloqueantes</h2><p className="text-muted">{idsBloqueados.length} {idsBloqueados.length === 1 ? 'equipo requiere' : 'equipos requieren'} atención antes de nuevas reservas.</p></div></div>
          {bloqueante.length === 0 ? <EstadoVacio titulo="Sin incidencias bloqueantes" descripcion="No hay averías sin resolver que bloqueen nuevas reservas. Las fechas y el estado activo se comprueban al reservar." /> : <ul className="detail-grid">{idsBloqueados.map((idEquipo) => <li key={idEquipo}><Link className="cell-title" to={`/admin/equipos/${idEquipo}`}>{equiposPorId.get(idEquipo)?.name ?? `Equipo #${idEquipo}`}</Link>{bloqueante.filter((incidencia) => incidencia.equipment_id === idEquipo).map((incidencia) => <div className="stack" key={incidencia.id}><Link to={`/admin/incidencias/${incidencia.id}`}>{incidencia.title}</Link><div className="inline-actions"><EtiquetaEstado clase={incidencia.status} /><EtiquetaEstado clase={incidencia.priority} /></div></div>)}</li>)}</ul>}
        </section>
      </div>
    </>}
  </>;
}
