import { useCallback, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, type FiltrosIncidencias, type PrioridadIncidencia, type EstadoIncidencia } from '../api/cliente';
import { EstadoVacio, Campo, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRecurso } from '../hooks/useRecurso';

export default function PaginaIncidencias() {
  const [idEquipo, establecerIdEquipo] = useState('');
  const [estado, establecerEstado] = useState('');
  const [prioridad, establecerPrioridad] = useState('');
  const [bloqueante, establecerBloqueante] = useState('');
  const [filtros, establecerFiltros] = useState<FiltrosIncidencias>({});
  const cargar = useCallback(async () => {
    const [incidencias, equipo] = await Promise.all([api.listarIncidencias(filtros), api.listarEquipos()]);
    return { incidencias, equipo };
  }, [filtros]);
  const { datos, cargando, error, recargar } = useRecurso(cargar);

  function aplicarFiltros(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    establecerFiltros({
      ...(idEquipo ? { equipment_id: Number(idEquipo) } : {}),
      ...(estado ? { status: estado as EstadoIncidencia } : {}),
      ...(prioridad ? { priority: prioridad as PrioridadIncidencia } : {}),
      ...(bloqueante ? { blocking: bloqueante === 'true' } : {}),
    });
  }

  function limpiarFiltros() {
    establecerIdEquipo(''); establecerEstado(''); establecerPrioridad(''); establecerBloqueante(''); establecerFiltros({});
  }

  return <>
    <CabeceraPagina titulo="Incidencias" descripcion="Avisos del cliente e incidencias internas. El bloqueo se decide desde administración."
      accion={<Link className="button" to="/admin/incidencias/nueva">Registrar incidencia</Link>} />
    <form className="panel filters" onSubmit={aplicarFiltros} aria-label="Filtros de incidencias">
      <Campo nombre="incident-equipment-filter" etiqueta="Equipo"><select id="incident-equipment-filter" value={idEquipo} onChange={(evento) => establecerIdEquipo(evento.target.value)}>
        <option value="">Todos los equipos</option>
        {datos?.equipo.map((equipo) => <option key={equipo.id} value={equipo.id}>{equipo.code} · {equipo.name}</option>)}
      </select></Campo>
      <Campo nombre="incident-status-filter" etiqueta="Estado"><select id="incident-status-filter" value={estado} onChange={(evento) => establecerEstado(evento.target.value)}>
        <option value="">Todos los estados</option><option value="open">Abierta</option><option value="in_progress">En curso</option><option value="resolved">Resuelta</option>
      </select></Campo>
      <Campo nombre="incident-priority-filter" etiqueta="Prioridad"><select id="incident-priority-filter" value={prioridad} onChange={(evento) => establecerPrioridad(evento.target.value)}>
        <option value="">Todas las prioridades</option><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
      </select></Campo>
      <Campo nombre="incident-blocking-filter" etiqueta="Bloqueo"><select id="incident-blocking-filter" value={bloqueante} onChange={(evento) => establecerBloqueante(evento.target.value)}>
        <option value="">Todas las incidencias</option><option value="true">Bloqueantes</option><option value="false">No bloqueantes</option>
      </select></Campo>
      <div className="inline-actions"><button className="button" type="submit" disabled={cargando}>Aplicar filtros</button><button className="button button-secondary" type="button" onClick={limpiarFiltros}>Limpiar filtros</button></div>
    </form>
    {error && <Aviso tono="error">{error} <button className="button button-secondary" type="button" onClick={recargar}>Volver a cargar</button></Aviso>}
    {cargando && <p role="status">Cargando incidencias…</p>}
    {datos && !cargando && !error && <section className="panel" aria-label="Listado de incidencias">
      <div className="panel-header"><h2>Incidencias registradas</h2><div className="inline-actions"><p className="text-muted">{datos.incidencias.length} resultados</p><button className="button button-secondary" type="button" disabled={cargando} onClick={recargar}>Actualizar listado</button></div></div>
      {datos.incidencias.length === 0 ? <EstadoVacio titulo="No hay incidencias con estos filtros" descripcion="Puedes cambiar los filtros o registrar una nueva incidencia." /> : <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table>
        <caption className="sr-only">Incidencias y estado de cada equipo</caption>
        <thead><tr><th scope="col">Incidencia</th><th scope="col">Origen y autor</th><th scope="col">Equipo</th><th scope="col">Prioridad</th><th scope="col">Estado</th><th scope="col">Bloqueo</th></tr></thead>
        <tbody>{datos.incidencias.map((incidencia) => {
          const equipo = datos.equipo.find((elementoLista) => elementoLista.id === incidencia.equipment_id);
          return <tr key={incidencia.id}>
            <td><Link className="cell-title" to={`/admin/incidencias/${incidencia.id}`}>{incidencia.title}</Link><span className="cell-subtitle">#{incidencia.id}</span></td>
            <td>{incidencia.reservation_id != null ? <><span>Aviso de cliente</span><Link className="cell-subtitle" to={`/admin/reservas/${incidencia.reservation_id}`}>Reserva #{incidencia.reservation_id}</Link></> : <span>Interna o histórica sin reserva vinculada</span>}<span className="cell-subtitle">{incidencia.author_user_id != null ? `Usuario #${incidencia.author_user_id}` : 'Sin autor de cuenta registrado'}</span></td>
            <td><Link to={`/admin/equipos/${incidencia.equipment_id}`}>{equipo?.code ?? `Equipo #${incidencia.equipment_id}`}</Link></td>
            <td><EtiquetaEstado clase={incidencia.priority} /></td><td><EtiquetaEstado clase={incidencia.status} /></td>
            <td>{incidencia.blocking ? (incidencia.status === 'resolved' ? 'Bloqueo resuelto' : 'Bloquea reservas') : 'No bloqueante'}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    </section>}
  </>;
}
