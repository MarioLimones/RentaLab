import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api, ErrorApi } from '../api/cliente';
import type { ReservaCliente, DisponibilidadPublica } from '../tipos/api';
import { Campo, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';
import { hoyEnMadrid } from './intervaloFechas';
import './cuenta.css';

export default function PaginaMiReserva() {
  const { id } = useParams();
  return <DetallesReserva key={id} idReserva={Number(id)} />;
}

function DetallesReserva({ idReserva }: { idReserva: number }) {
  const ubicacion = useLocation();
  const recurso = useRecurso(useCallback(async () => {
    if (!Number.isSafeInteger(idReserva) || idReserva <= 0) throw new Error('La reserva indicada no existe.');
    const reserva = await api.obtenerMiReserva(idReserva);
    try {
      const equipo = await api.obtenerEquipoPublico(reserva.equipment_id);
      return { reserva, nombreEquipo: equipo.name, equipoDisponible: true };
    } catch (error) {
      if (error instanceof ErrorApi && error.estado === 404) return { reserva, nombreEquipo: `Equipo #${reserva.equipment_id} (ficha no disponible)`, equipoDisponible: false };
      throw error;
    }
  }, [idReserva]));
  const [reservaGuardada, establecerReservaGuardada] = useState<ReservaCliente | null>(null);
  const [disponibilidadActualizada, establecerDisponibilidadActualizada] = useState<DisponibilidadPublica | null>(null);
  const [errorDisponibilidad, establecerErrorDisponibilidad] = useState(false);
  const [confirmandoCancelacion, establecerConfirmandoCancelacion] = useState(false);
  const [mostrarFormularioIncidencia, establecerMostrarFormularioIncidencia] = useState(false);
  const [incidenciaCreadaPara, establecerIncidenciaCreadaPara] = useState<number | null>(null);
  const [titulo, establecerTitulo] = useState('');
  const [descripcion, establecerDescripcion] = useState('');
  const cancelacion = useRetroalimentacionFormulario();
  const incidencia = useRetroalimentacionFormulario();
  const botonConfirmar = useRef<HTMLButtonElement>(null);
  const botonCancelar = useRef<HTMLButtonElement>(null);
  const encabezadoDetalles = useRef<HTMLHeadingElement>(null);
  const entradaTitulo = useRef<HTMLInputElement>(null);
  const botonInformar = useRef<HTMLButtonElement>(null);
  const confirmacionAnterior = useRef(false);
  const formularioIncidenciaAnterior = useRef(false);
  const cancelacionEnCurso = useRef(false);

  useEffect(() => {
    if (confirmandoCancelacion) botonConfirmar.current?.focus();
    else if (confirmacionAnterior.current) botonCancelar.current?.focus();
    confirmacionAnterior.current = confirmandoCancelacion;
  }, [confirmandoCancelacion]);
  useEffect(() => {
    if (mostrarFormularioIncidencia) entradaTitulo.current?.focus();
    else if (formularioIncidenciaAnterior.current) botonInformar.current?.focus();
    formularioIncidenciaAnterior.current = mostrarFormularioIncidencia;
  }, [mostrarFormularioIncidencia]);
  useEffect(() => {
    if (reservaGuardada?.id === idReserva && reservaGuardada.status === 'cancelled') encabezadoDetalles.current?.focus();
  }, [reservaGuardada, idReserva]);

  const datos = recurso.datos?.reserva.id === idReserva ? recurso.datos : null;
  const reserva = reservaGuardada?.id === idReserva ? reservaGuardada : datos?.reserva;
  const puedeCancelar = reserva?.status === 'confirmed' && hoyEnMadrid() < reserva.start_date;
  const creado = typeof ubicacion.state === 'object' && ubicacion.state !== null && 'created' in ubicacion.state && ubicacion.state.created === true;

  async function cancelarReserva() {
    if (cancelacionEnCurso.current) return;
    cancelacionEnCurso.current = true;
    cancelacion.limpiar();
    cancelacion.establecerPendiente(true);
    try {
      const actualizado = await api.cancelarMiReserva(idReserva);
      establecerReservaGuardada(actualizado);
      establecerConfirmandoCancelacion(false);
      establecerMostrarFormularioIncidencia(false);
      recurso.recargar();
      try {
        establecerDisponibilidadActualizada(await api.obtenerDisponibilidadPublica(actualizado.equipment_id, { start_date: actualizado.start_date, end_date: actualizado.end_date }));
        establecerErrorDisponibilidad(false);
      } catch {
        establecerErrorDisponibilidad(true);
      }
    } catch (error) {
      cancelacion.establecerFallo(error);
      recurso.recargar();
    } finally {
      cancelacionEnCurso.current = false;
      cancelacion.establecerPendiente(false);
    }
  }

  async function crearIncidencia(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (incidencia.pendiente) return;
    incidencia.limpiar();
    const errores: Record<string, string> = {};
    if (!titulo.trim()) errores.title = 'Escribe un título para el problema.';
    if (!descripcion.trim()) errores.description = 'Describe qué ha ocurrido con el equipo.';
    if (Object.keys(errores).length) { incidencia.establecerValidacion(errores); return; }
    incidencia.establecerPendiente(true);
    try {
      await api.crearMiIncidencia(idReserva, { title: titulo.trim(), description: descripcion.trim() });
      establecerIncidenciaCreadaPara(idReserva);
      establecerMostrarFormularioIncidencia(false);
      establecerTitulo('');
      establecerDescripcion('');
    } catch (error) {
      incidencia.establecerFallo(error);
    } finally {
      incidencia.establecerPendiente(false);
    }
  }

  return <div className="portal-account">
    <Link className="back-link" to="/mis-reservas">← Mis reservas</Link>
    <CabeceraPagina titulo={reserva ? `Reserva #${reserva.id}` : 'Detalle de tu reserva'} descripcion="Las fechas de alquiler se cuentan por días completos." />
    {recurso.cargando && <p role="status">Cargando tu reserva…</p>}
    {recurso.error && <Aviso tono="error">{recurso.error} <button className="button button-secondary" type="button" onClick={recurso.recargar}>Reintentar</button></Aviso>}
    {reserva && datos && <div className="portal-account-detail">
      <div className="portal-account-main">
        {reservaGuardada?.id === idReserva && reservaGuardada.status === 'cancelled'
          ? <><Aviso tono="success">Reserva cancelada. Puedes seguir consultando su historial.</Aviso>{disponibilidadActualizada && <p className="portal-account-muted">Disponibilidad actualizada: {disponibilidadActualizada.available ? 'el periodo vuelve a estar disponible.' : 'el equipo no está disponible para ese periodo; consulta su ficha para elegir otra opción.'}</p>}{errorDisponibilidad && <Aviso tono="warning">La cancelación se ha guardado. No se pudo actualizar la disponibilidad; vuelve a la ficha del equipo para consultarla.</Aviso>}</>
          : creado && <Aviso tono="success">Reserva #{reserva.id} confirmada. El equipo está reservado para las fechas indicadas.</Aviso>}
        <section className="portal-account-panel" aria-labelledby="reservation-details-heading">
          <div className="portal-account-panel-heading"><h2 ref={encabezadoDetalles} tabIndex={-1} id="reservation-details-heading">Datos de tu reserva</h2><EtiquetaEstado clase={reserva.status} /></div>
          <h3 className="portal-account-equipment">{datos.equipoDisponible ? <Link to={`/equipos/${reserva.equipment_id}`}>{datos.nombreEquipo}</Link> : datos.nombreEquipo}</h3>
          <dl className="portal-account-facts">
            <div><dt>Referencia</dt><dd>#{reserva.id}</dd></div>
            <div><dt>Inicio incluido</dt><dd><time dateTime={reserva.start_date}>{formatearFecha(reserva.start_date)}</time></dd></div>
            <div><dt>Fin excluido</dt><dd><time dateTime={reserva.end_date}>{formatearFecha(reserva.end_date)}</time></dd></div>
          </dl>
          <p className="portal-account-muted">El día de fin ya no forma parte de tu alquiler.</p>
        </section>
        {reserva.status === 'confirmed' && <section className="portal-account-panel" aria-labelledby="report-problem-heading">
          <h2 id="report-problem-heading">¿Hay algún problema con el equipo?</h2>
          <p>Cuéntanos qué ha ocurrido. Podrás seguir tu aviso y consultar la respuesta en Mis incidencias.</p>
          {incidenciaCreadaPara === idReserva && <Aviso tono="success">Aviso enviado. <Link to="/mis-incidencias">Consultar mis incidencias</Link></Aviso>}
          {mostrarFormularioIncidencia ? <form className="portal-account-incident-form" onSubmit={(evento) => { void crearIncidencia(evento); }} noValidate>
            {incidencia.mensaje && <Aviso tono="error" errores={incidencia.errores}>{incidencia.mensaje}</Aviso>}
            <Campo nombre="title" etiqueta="Título del problema" error={incidencia.errores.title}><input ref={entradaTitulo} name="title" value={titulo} onChange={(evento) => establecerTitulo(evento.target.value)} required maxLength={160} /></Campo>
            <Campo nombre="description" etiqueta="Descripción del problema" ayuda="Explica qué sucede y cómo lo has detectado." error={incidencia.errores.description}><textarea name="description" value={descripcion} onChange={(evento) => establecerDescripcion(evento.target.value)} required maxLength={2000} rows={5} /></Campo>
            <div className="inline-actions"><button className="button" type="submit" disabled={incidencia.pendiente}>{incidencia.pendiente ? 'Enviando aviso…' : 'Enviar aviso'}</button><button className="button button-secondary" type="button" disabled={incidencia.pendiente} onClick={() => establecerMostrarFormularioIncidencia(false)}>Volver a la reserva</button></div>
          </form> : <button ref={botonInformar} className="button button-secondary" type="button" onClick={() => { incidencia.limpiar(); establecerMostrarFormularioIncidencia(true); }}>Informar de un problema</button>}
        </section>}
      </div>
      {reserva.status === 'confirmed' && <aside className="portal-account-panel portal-account-cancellation" aria-label="Cancelación de tu reserva">
        <h2>Cancelar reserva</h2>
        {cancelacion.mensaje && <Aviso tono="error" errores={cancelacion.errores}>{cancelacion.mensaje}</Aviso>}
        {puedeCancelar ? <>
          <p>Puedes cancelar hasta el día anterior al inicio, según la fecha de Madrid. La reserva permanecerá en tu historial.</p>
          {confirmandoCancelacion ? <fieldset className="portal-account-confirmation"><legend>Confirmar cancelación</legend><p>¿Quieres cancelar la reserva #{reserva.id}?</p><button ref={botonConfirmar} className="button button-danger" type="button" disabled={cancelacion.pendiente} onClick={() => { void cancelarReserva(); }}>{cancelacion.pendiente ? 'Cancelando…' : 'Sí, cancelar reserva'}</button><button className="button button-secondary" type="button" disabled={cancelacion.pendiente} onClick={() => { establecerConfirmandoCancelacion(false); cancelacion.limpiar(); }}>Conservar reserva</button></fieldset>
            : <button ref={botonCancelar} className="button button-secondary" type="button" onClick={() => { cancelacion.limpiar(); establecerConfirmandoCancelacion(true); }}>Cancelar reserva</button>}
        </> : <p>El plazo de cancelación ha terminado: solo puedes cancelar antes del día de inicio, según la fecha de Madrid.</p>}
      </aside>}
    </div>}
  </div>;
}
