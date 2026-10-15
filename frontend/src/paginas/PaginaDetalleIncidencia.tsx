import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, type Incidencia, type ActualizacionIncidencia, type PrioridadIncidencia, type CambioEstadoIncidencia } from '../api/cliente';
import { Campo, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useRecurso } from '../hooks/useRecurso';
import '../administracion/incidencias.css';

function mensajeCreacion(estadoInterno: unknown): string | null {
  if (typeof estadoInterno === 'object' && estadoInterno !== null && 'success' in estadoInterno && typeof estadoInterno.success === 'string') return estadoInterno.success;
  return null;
}

function FormularioGestion({ incidencia, ocupado, errores, alGuardar }: {
  incidencia: Incidencia;
  ocupado: boolean;
  errores: Record<string, string>;
  alGuardar: (cambio: ActualizacionIncidencia) => Promise<boolean>;
}) {
  const [prioridad, establecerPrioridad] = useState<PrioridadIncidencia>(incidencia.priority);
  const [bloqueante, establecerBloqueante] = useState(incidencia.blocking);
  const [notasInternas, establecerNotasInternas] = useState(incidencia.internal_notes ?? '');
  const [respuestaPublica, establecerRespuestaPublica] = useState(incidencia.public_response ?? '');
  const [confirmando, establecerConfirmando] = useState(false);
  const botonConfirmar = useRef<HTMLButtonElement>(null);
  const botonGuardar = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (confirmando) botonConfirmar.current?.focus(); }, [confirmando]);

  async function guardar() {
    if (ocupado) return;
    const guardado = await alGuardar({ priority: prioridad, blocking: bloqueante, internal_notes: notasInternas, public_response: respuestaPublica });
    if (guardado) establecerConfirmando(false);
  }

  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (ocupado) return;
    if (bloqueante && !incidencia.blocking && incidencia.status !== 'resolved') establecerConfirmando(true);
    else void guardar();
  }

  return <section className="panel stack" aria-label="Prioridad, bloqueo y comunicación">
    <h2>Prioridad, bloqueo y comunicación</h2>
    <form className="stack" onSubmit={enviar} noValidate aria-busy={ocupado}>
      <Campo nombre="priority" etiqueta="Prioridad" error={errores.priority}><select id="priority" value={prioridad} disabled={ocupado || confirmando} onChange={(evento) => establecerPrioridad(evento.target.value as PrioridadIncidencia)}>
        <option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
      </select></Campo>
      <div className="checkbox-field"><input id="blocking" type="checkbox" checked={bloqueante} disabled={ocupado || confirmando} aria-invalid={Boolean(errores.blocking)} aria-describedby={errores.blocking ? 'blocking-hint blocking-error' : 'blocking-hint'} onChange={(evento) => establecerBloqueante(evento.target.checked)} /><label htmlFor="blocking">Bloquea nuevas reservas</label></div>
      <p id="blocking-hint" className="text-muted">La prioridad por sí sola no bloquea. Solo las incidencias bloqueantes sin resolver impiden nuevas reservas.</p>
      {errores.blocking && <p id="blocking-error" className="field-error">{errores.blocking}</p>}
      <Campo nombre="internal_notes" etiqueta="Notas internas" error={errores.internal_notes} ayuda="Solo administración. No se muestran al cliente; hasta 2000 caracteres."><textarea id="internal_notes" rows={4} maxLength={2000} disabled={ocupado || confirmando} value={notasInternas} onChange={(evento) => establecerNotasInternas(evento.target.value)} /></Campo>
      <Campo nombre="public_response" etiqueta="Respuesta visible al cliente" error={errores.public_response} ayuda={incidencia.reservation_id != null ? 'El cliente verá este texto en sus avisos; hasta 2000 caracteres.' : 'Esta incidencia no tiene una reserva vinculada. Guardar una respuesta no la asigna a ningún cliente.'}><textarea id="public_response" rows={4} maxLength={2000} disabled={ocupado || confirmando} value={respuestaPublica} onChange={(evento) => establecerRespuestaPublica(evento.target.value)} /></Campo>
      {confirmando ? <fieldset className="stack confirmation">
        <legend>Confirmar bloqueo del equipo</legend>
        <p>Se rechazarán nuevas reservas de este equipo hasta resolver o retirar el bloqueo. Las reservas confirmadas se conservan y no se cancelan automáticamente.</p>
        <div className="inline-actions">
          <button ref={botonConfirmar} className="button button-danger" type="button" disabled={ocupado} onClick={() => { void guardar(); }}>{ocupado ? 'Guardando…' : 'Sí, guardar y bloquear'}</button>
          <button className="button button-secondary" type="button" disabled={ocupado} onClick={() => { establecerConfirmando(false); queueMicrotask(() => botonGuardar.current?.focus()); }}>Volver a editar</button>
        </div>
      </fieldset> : <div className="form-actions"><button ref={botonGuardar} className="button" type="submit" disabled={ocupado}>{ocupado ? 'Guardando…' : 'Guardar gestión'}</button></div>}
    </form>
  </section>;
}

function DetalleIncidencia({ id }: { id: string | undefined }) {
  const ubicacion = useLocation();
  const [resolucion, establecerResolucion] = useState('');
  const [exito, establecerExito] = useState<string | null>(() => mensajeCreacion(ubicacion.state));
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  const cargar = useCallback(async () => {
    const idIncidencia = Number(id);
    if (!Number.isSafeInteger(idIncidencia) || idIncidencia <= 0) throw new Error('El identificador de la incidencia no es válido.');
    const [incidencia, equipo] = await Promise.all([api.obtenerIncidencia(idIncidencia), api.listarEquipos()]);
    return { incidencia, equipo: equipo.find((elementoLista) => elementoLista.id === incidencia.equipment_id) };
  }, [id]);
  const { datos, cargando, error, recargar } = useRecurso(cargar);
  const [conservado, establecerConservado] = useState<{ incidencia: Incidencia; fuente: typeof datos; accion: 'status' | 'management' } | null>(null);
  // Conserva como válida una escritura completada aunque falle el GET posterior. Un nuevo GET
  // sustituye la instantánea, incluidos el aviso calculado y las reservas.
  const incidencia = conservado && conservado.fuente === datos ? conservado.incidencia : datos?.incidencia;
  const encabezadoDetalle = useRef<HTMLHeadingElement>(null);
  const entradaResolucion = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!conservado) return;
    if (conservado.accion === 'management' || conservado.incidencia.status === 'resolved') encabezadoDetalle.current?.focus();
    else entradaResolucion.current?.focus();
  }, [conservado]);

  async function guardarGestion(cambio: ActualizacionIncidencia): Promise<boolean> {
    if (!datos || !incidencia || retroalimentacionFormulario.pendiente) return false;
    retroalimentacionFormulario.limpiar(); establecerExito(null); retroalimentacionFormulario.establecerPendiente(true);
    try {
      const guardado = await api.modificarIncidencia(incidencia.id, cambio);
      establecerConservado({ incidencia: guardado, fuente: datos, accion: 'management' });
      establecerExito('Gestión de la incidencia guardada.');
      recargar();
      return true;
    } catch (fallo: unknown) {
      retroalimentacionFormulario.establecerFallo(fallo);
      return false;
    } finally {
      retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  async function cambiarEstado(cambio: CambioEstadoIncidencia) {
    if (!datos || !incidencia || retroalimentacionFormulario.pendiente) return;
    retroalimentacionFormulario.limpiar(); establecerExito(null); retroalimentacionFormulario.establecerPendiente(true);
    try {
      const guardado = await api.cambiarEstadoIncidencia(incidencia.id, cambio);
      establecerConservado({ incidencia: guardado, fuente: datos, accion: 'status' });
      establecerExito(cambio.status === 'resolved' ? 'Incidencia resuelta. Se conserva su historial.' : 'La incidencia está en curso.');
      recargar();
    } catch (fallo: unknown) {
      retroalimentacionFormulario.establecerFallo(fallo);
    } finally {
      retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  function resolver(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    retroalimentacionFormulario.limpiar();
    if (!resolucion.trim()) {
      retroalimentacionFormulario.establecerValidacion({ resolution: 'Explica cómo se ha resuelto la incidencia.' });
      return;
    }
    void cambiarEstado({ status: 'resolved', resolution: resolucion.trim() });
  }

  return <>
    <Link className="back-link" to="/admin/incidencias">Volver a incidencias</Link>
    {cargando && <p role="status">Cargando incidencia…</p>}
    {error && <Aviso tono="error">{error} <button className="button button-secondary" type="button" onClick={recargar}>Volver a cargar</button></Aviso>}
    {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
    {exito && <Aviso tono="success">{exito}</Aviso>}
    {datos && incidencia && <>
      <CabeceraPagina titulo={incidencia.title} descripcion={`Incidencia #${incidencia.id}`} />
      <section className="panel stack admin-incident-detail" aria-label="Detalle de incidencia">
        <div className="panel-header"><h2 ref={encabezadoDetalle} tabIndex={-1}>Datos de la incidencia</h2><div className="inline-actions"><EtiquetaEstado clase={incidencia.status} /><EtiquetaEstado clase={incidencia.priority} /></div></div>
        <dl className="detail-list">
          <div><dt>Equipo</dt><dd><Link to={`/admin/equipos/${incidencia.equipment_id}`}>{datos.equipo ? `${datos.equipo.code} · ${datos.equipo.name}` : `Equipo #${incidencia.equipment_id}`}</Link></dd></div>
          <div><dt>Origen</dt><dd>{incidencia.reservation_id != null ? 'Aviso de cliente' : 'Interna o histórica sin reserva vinculada'}</dd></div>
          <div><dt>Reserva vinculada</dt><dd>{incidencia.reservation_id != null ? <Link to={`/admin/reservas/${incidencia.reservation_id}`}>Reserva #{incidencia.reservation_id}</Link> : 'Sin reserva vinculada'}</dd></div>
          <div><dt>Autor</dt><dd>{incidencia.author_user_id != null ? `Usuario #${incidencia.author_user_id}` : 'Sin autor de cuenta registrado'}</dd></div>
          <div><dt>Descripción</dt><dd>{incidencia.description || 'Sin descripción.'}</dd></div>
          <div><dt>Bloqueo</dt><dd>{incidencia.blocking ? (incidencia.status === 'resolved' ? 'Incidencia bloqueante resuelta.' : 'Impide nuevas reservas de este equipo.') : 'No impide nuevas reservas.'}</dd></div>
        </dl>
        {incidencia.warning && <Aviso tono="warning">{incidencia.warning}</Aviso>}
        {incidencia.confirmed_reservation_ids.length > 0 && <div><h2>Reservas confirmadas del equipo</h2><p className="text-muted">Reservas actualmente confirmadas de esta unidad, sin filtro de fechas. El bloqueo no las modifica.</p><ul>{incidencia.confirmed_reservation_ids.map((idReserva) => <li key={idReserva}><Link to={`/admin/reservas/${idReserva}`}>Reserva #{idReserva}</Link></li>)}</ul></div>}
        {incidencia.status === 'resolved' && <div><h2>Resolución interna</h2><p className="admin-incident-text">{incidencia.resolution}</p><p className="text-muted">La disponibilidad también depende de otras incidencias, del estado activo y del intervalo de reserva.</p></div>}
      </section>
      <FormularioGestion key={JSON.stringify([incidencia.priority, incidencia.blocking, incidencia.internal_notes, incidencia.public_response])} incidencia={incidencia} ocupado={retroalimentacionFormulario.pendiente || cargando} errores={retroalimentacionFormulario.errores} alGuardar={guardarGestion} />
      {incidencia.status !== 'resolved' && <section className="panel stack" aria-label="Gestionar estado de incidencia">
        <h2>Estado y resolución interna</h2>
        {incidencia.status === 'open' && <div><button className="button button-secondary" type="button" disabled={retroalimentacionFormulario.pendiente || cargando} onClick={() => { void cambiarEstado({ status: 'in_progress' }); }}>Iniciar trabajo</button></div>}
        <form className="stack" onSubmit={resolver} noValidate aria-busy={retroalimentacionFormulario.pendiente}>
          <Campo nombre="resolution" etiqueta="Resolución" error={retroalimentacionFormulario.errores.resolution} ayuda="Obligatoria para cerrar. Es interna y no se copia a la respuesta visible al cliente."><textarea ref={entradaResolucion} id="resolution" required maxLength={2000} rows={4} disabled={retroalimentacionFormulario.pendiente || cargando} value={resolucion} onChange={(evento) => establecerResolucion(evento.target.value)} /></Campo>
          <p className="text-muted">Resolver retira este bloqueo. El equipo solo admitirá nuevas reservas si sigue activo, no quedan otros bloqueos y el intervalo está libre.</p>
          <div className="form-actions"><button className="button" type="submit" disabled={retroalimentacionFormulario.pendiente || cargando}>{retroalimentacionFormulario.pendiente ? 'Guardando…' : 'Resolver incidencia'}</button></div>
        </form>
      </section>}
    </>}
  </>;
}

export default function PaginaDetalleIncidencia() {
  const { id } = useParams();
  return <DetalleIncidencia key={id} id={id} />;
}
