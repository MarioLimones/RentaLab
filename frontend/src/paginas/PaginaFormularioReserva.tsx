import { useCallback, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/cliente';
import type { Disponibilidad } from '../api/cliente';
import { EstadoVacio, Campo, Aviso, CabeceraPagina } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useEstaMontado } from '../hooks/useEstaMontado';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';

const mensajesDisponibilidad: Record<NonNullable<Disponibilidad['reason']>, string> = {
  equipment_inactive: 'El equipo está inactivo.',
  blocking_incident: 'El equipo tiene una incidencia bloqueante sin resolver.',
  reservation_overlap: 'El equipo tiene una reserva confirmada que solapa este intervalo.',
};

export default function PaginaFormularioReserva() {
  const navegar = useNavigate();
  const estaMontado = useEstaMontado();
  const [busqueda] = useSearchParams();
  const equipoInicial = busqueda.get('equipment_id') ?? '';
  const [idEquipo, establecerIdEquipo] = useState(/^\d+$/.test(equipoInicial) ? equipoInicial : '');
  const [nombreCliente, establecerNombreCliente] = useState('');
  const [correoCliente, establecerCorreoCliente] = useState('');
  const [fechaInicio, establecerFechaInicio] = useState('');
  const [fechaFin, establecerFechaFin] = useState('');
  const [referenciaExterna, establecerReferenciaExterna] = useState('');
  const equipo = useRecurso(useCallback(() => api.listarEquipos(), []));
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  const [disponibilidad, establecerDisponibilidad] = useState<Disponibilidad | null>(null);
  const [comprobando, establecerComprobando] = useState(false);
  const [errorDisponibilidad, establecerErrorDisponibilidad] = useState<string | null>(null);
  const solicitudDisponibilidad = useRef(0);

  function invalidarDisponibilidad() {
    solicitudDisponibilidad.current += 1;
    establecerDisponibilidad(null);
    establecerErrorDisponibilidad(null);
    establecerComprobando(false);
  }

  function erroresIntervalo(): Record<string, string> {
    const errores: Record<string, string> = {};
    if (!idEquipo) errores.equipment_id = 'Selecciona un equipo.';
    if (!fechaInicio) errores.start_date = 'Indica la fecha de inicio.';
    if (!fechaFin) errores.end_date = 'Indica la fecha de fin.';
    if (fechaInicio && fechaFin && fechaFin <= fechaInicio) errores.end_date = 'La fecha de fin debe ser posterior al inicio.';
    return errores;
  }

  async function comprobarDisponibilidad() {
    retroalimentacionFormulario.limpiar();
    const errores = erroresIntervalo();
    if (Object.keys(errores).length > 0) {
      retroalimentacionFormulario.establecerValidacion(errores);
      return;
    }
    const idSolicitud = ++solicitudDisponibilidad.current;
    establecerComprobando(true);
    establecerDisponibilidad(null);
    establecerErrorDisponibilidad(null);
    try {
      const resultado = await api.obtenerDisponibilidadEquipo(Number(idEquipo), { start_date: fechaInicio, end_date: fechaFin });
      if (estaMontado() && idSolicitud === solicitudDisponibilidad.current) establecerDisponibilidad(resultado);
    } catch (error) {
      if (estaMontado() && idSolicitud === solicitudDisponibilidad.current) {
        establecerErrorDisponibilidad(error instanceof Error ? error.message : 'No se pudo consultar la disponibilidad. Vuelve a intentarlo.');
      }
    } finally {
      if (estaMontado() && idSolicitud === solicitudDisponibilidad.current) establecerComprobando(false);
    }
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    retroalimentacionFormulario.limpiar();
    const errores = erroresIntervalo();
    if (!nombreCliente.trim()) errores.customer_name = 'Indica el nombre del cliente.';
    if (!correoCliente.trim()) errores.customer_email = 'Indica el correo del cliente.';
    else if (!evento.currentTarget.querySelector<HTMLInputElement>('#customer_email')?.validity.valid) {
      errores.customer_email = 'Introduce un correo válido, por ejemplo cliente@example.test.';
    }
    if (Object.keys(errores).length > 0) {
      retroalimentacionFormulario.establecerValidacion(errores);
      return;
    }
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      const resultado = await api.crearReserva({
        equipment_id: Number(idEquipo), customer_name: nombreCliente, customer_email: correoCliente,
        start_date: fechaInicio, end_date: fechaFin, external_reference: referenciaExterna.trim() || null,
      });
      if (!estaMontado()) return;
      navegar(`/admin/reservas/${resultado.id}`, { state: { created: true } });
    } catch (error) {
      if (estaMontado()) retroalimentacionFormulario.establecerFallo(error);
    } finally {
      if (estaMontado()) retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  const equipoSeleccionado = equipo.datos?.find((elementoLista) => elementoLista.id === Number(idEquipo));

  return <>
    <Link className="back-link" to="/admin/reservas">← Reservas</Link>
    <CabeceraPagina titulo="Nueva reserva" descripcion="Cada reserva corresponde a una unidad física. El servidor confirma el equipo y el intervalo al guardar." />
    {equipo.cargando && <p role="status">Cargando equipos…</p>}
    {equipo.error && <Aviso tono="error">{equipo.error} <button className="button button-secondary" type="button" onClick={equipo.recargar}>Reintentar</button></Aviso>}
    {equipo.datos?.length === 0 && <EstadoVacio titulo="Todavía no hay equipos" descripcion="Crea una unidad antes de registrar una reserva." accion={<Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link>} />}
    {equipo.datos && equipo.datos.length > 0 && <form className="panel stack" onSubmit={(evento) => { void enviar(evento); }} noValidate>
      {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
      <div className="form-grid">
        <Campo nombre="equipment_id" etiqueta="Equipo" error={retroalimentacionFormulario.errores.equipment_id}>
          <select id="equipment_id" name="equipment_id" value={idEquipo} onChange={(evento) => { establecerIdEquipo(evento.target.value); invalidarDisponibilidad(); }} required>
            <option value="">Selecciona un equipo</option>
            {equipo.datos.map((elementoLista) => <option key={elementoLista.id} value={elementoLista.id}>{elementoLista.code} · {elementoLista.name}{elementoLista.active ? '' : ' (inactivo)'}</option>)}
          </select>
        </Campo>
        <Campo nombre="external_reference" etiqueta="Referencia externa (opcional)" error={retroalimentacionFormulario.errores.external_reference} ayuda="La referencia es única y se conserva al cancelar.">
          <input id="external_reference" name="external_reference" value={referenciaExterna} onChange={(evento) => { establecerReferenciaExterna(evento.target.value); }} maxLength={120} />
        </Campo>
        <Campo nombre="customer_name" etiqueta="Nombre del cliente" error={retroalimentacionFormulario.errores.customer_name}>
          <input id="customer_name" name="customer_name" value={nombreCliente} onChange={(evento) => { establecerNombreCliente(evento.target.value); }} autoComplete="name" maxLength={120} required />
        </Campo>
        <Campo nombre="customer_email" etiqueta="Correo del cliente" error={retroalimentacionFormulario.errores.customer_email}>
          <input id="customer_email" name="customer_email" type="email" value={correoCliente} onChange={(evento) => { establecerCorreoCliente(evento.target.value); }} autoComplete="email" maxLength={254} required />
        </Campo>
        <Campo nombre="start_date" etiqueta="Fecha de inicio" error={retroalimentacionFormulario.errores.start_date} ayuda="El primer día de alquiler está incluido.">
          <input id="start_date" name="start_date" type="date" value={fechaInicio} onChange={(evento) => { establecerFechaInicio(evento.target.value); invalidarDisponibilidad(); }} required />
        </Campo>
        <Campo nombre="end_date" etiqueta="Fecha de fin" error={retroalimentacionFormulario.errores.end_date} ayuda="El día de devolución está excluido; otra reserva puede comenzar ese día.">
          <input id="end_date" name="end_date" type="date" value={fechaFin} onChange={(evento) => { establecerFechaFin(evento.target.value); invalidarDisponibilidad(); }} required />
        </Campo>
      </div>
      <div className="stack">
        <div><button className="button button-secondary" type="button" onClick={() => { void comprobarDisponibilidad(); }} disabled={comprobando || retroalimentacionFormulario.pendiente}>{comprobando ? 'Consultando…' : 'Consultar disponibilidad'}</button></div>
        <p className="text-muted">La consulta es orientativa: no retiene el equipo. La disponibilidad se comprueba de nuevo al crear.</p>
        {errorDisponibilidad && <Aviso tono="error">{errorDisponibilidad}</Aviso>}
        {disponibilidad && <section className="panel" aria-label="Resultado de disponibilidad" aria-live="polite">
          <p className="cell-title">{equipoSeleccionado?.code ?? `Equipo #${disponibilidad.equipment_id}`} · {equipoSeleccionado?.name}</p>
          <p>Del {formatearFecha(disponibilidad.start_date)} al {formatearFecha(disponibilidad.end_date)} (fin excluido).</p>
          <Aviso tono={disponibilidad.available ? 'success' : 'warning'}>{disponibilidad.available ? 'Disponible para este intervalo.' : disponibilidad.reason ? mensajesDisponibilidad[disponibilidad.reason] : 'No disponible para este intervalo.'}</Aviso>
        </section>}
      </div>
      <div className="form-actions">
        <button className="button" type="submit" disabled={retroalimentacionFormulario.pendiente}>{retroalimentacionFormulario.pendiente ? 'Creando…' : 'Crear reserva'}</button>
        <Link className="button button-secondary" to="/admin/reservas">Volver al listado</Link>
      </div>
    </form>}
  </>;
}
