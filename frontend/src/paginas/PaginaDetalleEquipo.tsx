import { useCallback, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, type Equipo } from '../api/cliente';
import { EstadoVacio, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';

function avisoRuta(estadoInterno: unknown): string | null {
  return typeof estadoInterno === 'object' && estadoInterno !== null && 'notice' in estadoInterno && typeof estadoInterno.notice === 'string' ? estadoInterno.notice : null;
}

function DetalleEquipo({ idEquipo }: { idEquipo: number }) {
  const cargar = useCallback(async () => {
    const [equipo, reservas, incidencias] = await Promise.all([
      api.obtenerEquipo(idEquipo), api.listarReservas({ equipment_id: idEquipo }), api.listarIncidencias({ equipment_id: idEquipo }),
    ]);
    return { equipo, reservas, incidencias };
  }, [idEquipo]);
  const { datos, cargando, error, recargar } = useRecurso(cargar);
  const [actualizado, establecerActualizado] = useState<{ fuente: Equipo; valor: Equipo } | null>(null);
  const [exito, establecerExito] = useState<string | null>(null);
  const cambiando = useRef(false);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  const ubicacion = useLocation();
  const aviso = avisoRuta(ubicacion.state);

  async function alternarActivo(equipo: Equipo) {
    if (cambiando.current || cargando || !datos) return;
    cambiando.current = true;
    retroalimentacionFormulario.limpiar();
    establecerExito(null);
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      const guardado = await api.modificarEquipo(equipo.id, { active: !equipo.active });
      establecerActualizado({ fuente: datos.equipo, valor: guardado });
      establecerExito(`Equipo ${guardado.active ? 'activado' : 'desactivado'} correctamente.`);
      recargar();
    } catch (fallo) {
      retroalimentacionFormulario.establecerFallo(fallo);
    } finally {
      cambiando.current = false;
      retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  if (cargando && !datos) return <p role="status">Cargando equipo y actividad…</p>;
  if (error && !datos) return <><CabeceraPagina titulo="Detalle del equipo" /><Aviso tono="error">{error} <button type="button" className="button button-secondary" onClick={recargar}>Volver a cargar</button></Aviso><Link to="/admin/equipos">Volver a equipos</Link></>;
  if (!datos) return null;
  const equipo = actualizado?.fuente === datos.equipo ? actualizado.valor : datos.equipo;
  const bloqueante = datos.incidencias.filter((incidencia) => incidencia.blocking && incidencia.status !== 'resolved');

  return <>
    <Link className="back-link" to="/admin/equipos">← Volver a equipos</Link>
    <CabeceraPagina titulo={equipo.name} descripcion={`${equipo.code} · ${equipo.category}`} accion={<div className="inline-actions"><button className="button button-secondary" type="button" disabled={cargando || retroalimentacionFormulario.pendiente} onClick={recargar}>Actualizar datos</button><Link className="button button-secondary" to={`/admin/equipos/${equipo.id}/editar`}>Editar equipo</Link></div>} />
    {cargando && <p role="status">Actualizando equipo y actividad…</p>}
    {error && <Aviso tono="error">{error} <button type="button" className="button button-secondary" onClick={recargar}>Volver a cargar</button></Aviso>}
    {(exito ?? aviso) && <Aviso tono="success">{exito ?? aviso}</Aviso>}
    {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
    {bloqueante.length > 0 && <Aviso tono="warning">Este equipo tiene {bloqueante.length} {bloqueante.length === 1 ? 'incidencia bloqueante sin resolver' : 'incidencias bloqueantes sin resolver'}. Impiden nuevas reservas. El equipo también debe estar activo para admitirlas.</Aviso>}
    <section className="panel" aria-labelledby="equipment-data-title">
      <div className="panel-header"><h2 id="equipment-data-title">Datos del equipo</h2><EtiquetaEstado clase={equipo.active ? 'active' : 'inactive'} /></div>
      <dl className="detail-list"><div><dt>Código</dt><dd>{equipo.code}</dd></div><div><dt>Categoría</dt><dd>{equipo.category}</dd></div><div><dt>Descripción interna</dt><dd>{equipo.description || 'Sin descripción interna.'}</dd></div></dl>
      <div className="inline-actions"><button type="button" className="button button-secondary" disabled={retroalimentacionFormulario.pendiente || cargando} onClick={() => { void alternarActivo(equipo); }}>{retroalimentacionFormulario.pendiente ? 'Guardando…' : equipo.active ? 'Desactivar equipo' : 'Activar equipo'}</button><Link className="button" to={`/admin/reservas/nueva?equipment_id=${equipo.id}`}>Crear reserva</Link><Link className="button button-secondary" to={`/admin/incidencias/nueva?equipment_id=${equipo.id}`}>Registrar incidencia</Link></div>
      {!equipo.active && <p className="text-muted">El equipo inactivo conserva su historial y no admite nuevas reservas.</p>}
    </section>
    <section className="panel" aria-labelledby="equipment-public-title">
      <div className="panel-header"><h2 id="equipment-public-title">Ficha pública del catálogo</h2>{equipo.active && <Link to={`/equipos/${equipo.id}`}>Ver ficha pública</Link>}</div>
      <dl className="detail-list"><div><dt>Descripción pública</dt><dd>{equipo.public_description || 'Sin descripción pública.'}</dd></div><div><dt>Imagen</dt><dd>{equipo.image_url || 'Alternativa local de RentaLab.'}</dd></div></dl>
      <h3>Características técnicas</h3>
      {Object.keys(equipo.technical_specs ?? {}).length === 0 ? <p className="text-muted">Sin características técnicas.</p> : <dl className="detail-list">{Object.entries(equipo.technical_specs ?? {}).map(([nombre, valor]) => <div key={nombre}><dt>{nombre}</dt><dd>{valor}</dd></div>)}</dl>}
      {!equipo.active && <p className="text-muted">El equipo inactivo queda fuera del catálogo público.</p>}
      <Link to="/catalogo">Abrir catálogo de clientes</Link>
    </section>
    <div className="split-grid">
      <section className="panel" aria-labelledby="equipment-reservations-title"><div className="panel-header"><h2 id="equipment-reservations-title">Reservas del equipo</h2><span className="text-muted">{datos.reservas.length} en total</span></div>
        {datos.reservas.length === 0 ? <EstadoVacio titulo="Sin reservas" descripcion="Las reservas de esta unidad aparecerán aquí, también las canceladas." /> : <ul className="detail-grid">{datos.reservas.map((reserva) => <li key={reserva.id}><Link className="cell-title" to={`/admin/reservas/${reserva.id}`}>{reserva.customer_name} · #{reserva.id}</Link><p>{formatearFecha(reserva.start_date)} → {formatearFecha(reserva.end_date)} <span className="text-muted">(fin excluido)</span></p><EtiquetaEstado clase={reserva.status} /></li>)}</ul>}
      </section>
      <section className="panel" aria-labelledby="equipment-incidents-title"><div className="panel-header"><h2 id="equipment-incidents-title">Incidencias del equipo</h2><span className="text-muted">{datos.incidencias.length} en total</span></div>
        {datos.incidencias.length === 0 ? <EstadoVacio titulo="Sin incidencias" descripcion="No hay incidencias registradas para esta unidad." /> : <ul className="detail-grid">{datos.incidencias.map((incidencia) => <li key={incidencia.id}><Link className="cell-title" to={`/admin/incidencias/${incidencia.id}`}>{incidencia.title}</Link><div className="inline-actions"><EtiquetaEstado clase={incidencia.status} /><EtiquetaEstado clase={incidencia.priority} />{incidencia.blocking && <EtiquetaEstado clase="blocking" />}</div></li>)}</ul>}
      </section>
    </div>
  </>;
}

export function PaginaDetalleEquipo() {
  const { id } = useParams();
  const idEquipo = Number(id);
  if (!Number.isSafeInteger(idEquipo) || idEquipo <= 0) return <><CabeceraPagina titulo="Equipo no válido" /><Aviso tono="error">El identificador del equipo no es válido.</Aviso><Link to="/admin/equipos">Volver a equipos</Link></>;
  return <DetalleEquipo key={idEquipo} idEquipo={idEquipo} />;
}
