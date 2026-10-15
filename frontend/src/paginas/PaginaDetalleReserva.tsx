import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { api } from '../api/cliente';
import type { Reserva } from '../api/cliente';
import { Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';
import { origenReserva, titularReserva } from '../administracion/etiquetasReserva';

export default function PaginaDetalleReserva() {
  const { id } = useParams();
  return <DetallesReserva key={id} idReserva={Number(id)} />;
}

function DetallesReserva({ idReserva }: { idReserva: number }) {
  const ubicacion = useLocation();
  const recurso = useRecurso(useCallback(async () => {
    if (!Number.isSafeInteger(idReserva) || idReserva <= 0) throw new Error('La reserva indicada no existe.');
    const reserva = await api.obtenerReserva(idReserva);
    const equipo = await api.obtenerEquipo(reserva.equipment_id);
    return { reserva, equipo };
  }, [idReserva]));
  const [reservaGuardada, establecerReservaGuardada] = useState<Reserva | null>(null);
  const [confirmando, establecerConfirmando] = useState(false);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  const botonConfirmar = useRef<HTMLButtonElement>(null);
  const botonCancelar = useRef<HTMLButtonElement>(null);
  const encabezadoDetalle = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (confirmando) botonConfirmar.current?.focus();
    else botonCancelar.current?.focus();
  }, [confirmando]);

  useEffect(() => {
    if (reservaGuardada?.id === idReserva && reservaGuardada.status === 'cancelled') {
      encabezadoDetalle.current?.focus();
    }
  }, [reservaGuardada, idReserva]);

  async function cancelarReserva() {
    if (retroalimentacionFormulario.pendiente) return;
    retroalimentacionFormulario.limpiar();
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      const respuesta = await api.cancelarReserva(idReserva);
      establecerReservaGuardada(respuesta);
      establecerConfirmando(false);
      recurso.recargar();
    } catch (error) {
      retroalimentacionFormulario.establecerFallo(error);
    } finally {
      retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  const reserva = reservaGuardada?.id === idReserva ? reservaGuardada
    : recurso.datos?.reserva.id === idReserva ? recurso.datos.reserva : undefined;
  const equipo = recurso.datos?.reserva.id === idReserva ? recurso.datos.equipo : undefined;
  const creado = typeof ubicacion.state === 'object' && ubicacion.state !== null
    && 'created' in ubicacion.state && ubicacion.state.created === true;

  return <>
    <Link className="back-link" to="/admin/reservas">← Reservas</Link>
    <CabeceraPagina titulo={reserva ? `Reserva #${reserva.id}` : 'Detalle de reserva'} descripcion="El historial mantiene el cliente, las fechas y la referencia también después de cancelar." />
    {recurso.cargando && <p role="status">Cargando reserva…</p>}
    {recurso.error && <Aviso tono="error">{recurso.error} <button className="button button-secondary" type="button" onClick={recurso.recargar}>Reintentar</button></Aviso>}
    {reserva && equipo && <div className="stack">
      {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
      {reservaGuardada?.id === reserva.id && reservaGuardada.status === 'cancelled'
        ? <Aviso tono="success">Reserva cancelada. Se conserva su historial y deja de bloquear el intervalo.</Aviso>
        : creado && <Aviso tono="success">Reserva creada y confirmada.</Aviso>}
      <section className="panel">
        <div className="panel-header"><h2 ref={encabezadoDetalle} tabIndex={-1}>Datos de la reserva</h2><EtiquetaEstado clase={reserva.status} /></div>
        <dl className="detail-list">
          <div><dt>Equipo</dt><dd><Link to={`/admin/equipos/${equipo.id}`}>{equipo.code} · {equipo.name}</Link></dd></div>
          <div><dt>Cliente</dt><dd>{reserva.customer_name}</dd></div>
          <div><dt>Correo</dt><dd>{reserva.customer_email}</dd></div>
          <div><dt>Propietario de cuenta</dt><dd>{reserva.customer_user_id ? <Link to={`/admin/reservas?customer_user_id=${reserva.customer_user_id}`}>{titularReserva(reserva)}</Link> : titularReserva(reserva)}</dd></div>
          <div><dt>Origen</dt><dd>{origenReserva(reserva)}</dd></div>
          <div><dt>Inicio incluido</dt><dd>{formatearFecha(reserva.start_date)}</dd></div>
          <div><dt>Fin excluido</dt><dd>{formatearFecha(reserva.end_date)}</dd></div>
          <div><dt>Referencia externa</dt><dd>{reserva.external_reference ?? 'Sin referencia externa'}</dd></div>
        </dl>
      </section>
      {reserva.status === 'confirmed' && <section className="panel stack" aria-label="Cancelación de reserva">
        <h2>Cancelar reserva</h2>
        <p>La cancelación conserva todos los datos y se reflejará en la cuenta del propietario al volver a consultar. Otras reservas, incidencias o el estado del equipo pueden seguir impidiendo nuevos alquileres.</p>
        {confirmando ? <fieldset className="stack">
          <legend>Confirmar cancelación</legend>
          <p>¿Quieres cancelar la reserva #{reserva.id}? Su historial se conservará.</p>
          <div className="inline-actions">
            <button ref={botonConfirmar} className="button button-danger" type="button" disabled={retroalimentacionFormulario.pendiente} onClick={() => { void cancelarReserva(); }}>{retroalimentacionFormulario.pendiente ? 'Cancelando…' : 'Sí, cancelar reserva'}</button>
            <button className="button button-secondary" type="button" disabled={retroalimentacionFormulario.pendiente} onClick={() => { establecerConfirmando(false); retroalimentacionFormulario.limpiar(); }}>Volver</button>
          </div>
        </fieldset> : <div><button ref={botonCancelar} className="button button-danger" type="button" onClick={() => { retroalimentacionFormulario.limpiar(); establecerConfirmando(true); }}>Cancelar reserva</button></div>}
      </section>}
    </div>}
  </>;
}
