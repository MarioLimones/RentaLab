import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/cliente';
import type { FiltrosReservas, OrigenReserva, EstadoReserva } from '../api/cliente';
import { origenReserva, origenesReserva, titularReserva } from '../administracion/etiquetasReserva';
import { EstadoVacio, Campo, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useRecurso } from '../hooks/useRecurso';
import { formatearFecha } from '../utilidades/fechas';

export default function PaginaReservas() {
  const [busqueda] = useSearchParams();
  const titularInicial = busqueda.get('customer_user_id') ?? '';
  const titularInicialValido = /^[1-9]\d*$/.test(titularInicial) && Number.isSafeInteger(Number(titularInicial)) ? titularInicial : '';
  const [cliente, establecerCliente] = useState('');
  const [idUsuarioCliente, establecerIdUsuarioCliente] = useState(titularInicialValido);
  const [origen, establecerOrigen] = useState<OrigenReserva | ''>('');
  const [idEquipo, establecerIdEquipo] = useState('');
  const [estado, establecerEstado] = useState<EstadoReserva | ''>('');
  const [fechaInicio, establecerFechaInicio] = useState('');
  const [fechaFin, establecerFechaFin] = useState('');
  const [filtros, establecerFiltros] = useState<FiltrosReservas>(titularInicialValido ? { customer_user_id: Number(titularInicialValido) } : {});
  const equipo = useRecurso(useCallback(() => api.listarEquipos(), []));
  const reservas = useRecurso(useCallback(() => api.listarReservas(filtros), [filtros]));
  const retroalimentacionFormulario = useRetroalimentacionFormulario();

  function aplicarFiltros(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    retroalimentacionFormulario.limpiar();
    const errores: Record<string, string> = {};
    if (idUsuarioCliente && (!/^[1-9]\d*$/.test(idUsuarioCliente) || !Number.isSafeInteger(Number(idUsuarioCliente)))) errores.customer_user_id = 'Indica un identificador de cuenta positivo.';
    if (Boolean(fechaInicio) !== Boolean(fechaFin)) {
      errores[fechaInicio ? 'end_date' : 'start_date'] = 'Indica ambas fechas para filtrar por intervalo.';
    } else if (fechaInicio && fechaFin <= fechaInicio) {
      errores.end_date = 'La fecha de fin debe ser posterior al inicio.';
    }
    if (Object.keys(errores).length > 0) {
      retroalimentacionFormulario.establecerValidacion(errores);
      return;
    }
    establecerFiltros({
      ...(cliente.trim() ? { customer: cliente.trim() } : {}),
      ...(idUsuarioCliente ? { customer_user_id: Number(idUsuarioCliente) } : {}),
      ...(origen ? { origin: origen } : {}),
      ...(idEquipo ? { equipment_id: Number(idEquipo) } : {}),
      ...(estado ? { status: estado } : {}),
      ...(fechaInicio && fechaFin ? { start_date: fechaInicio, end_date: fechaFin } : {}),
    });
  }

  function restablecerFiltros() {
    establecerCliente('');
    establecerIdUsuarioCliente('');
    establecerOrigen('');
    establecerIdEquipo('');
    establecerEstado('');
    establecerFechaInicio('');
    establecerFechaFin('');
    retroalimentacionFormulario.limpiar();
    establecerFiltros({});
  }

  return <>
    <CabeceraPagina titulo="Reservas" descripcion="Consulta el historial y organiza los alquileres por días completos." accion={<Link className="button" to="/admin/reservas/nueva">Nueva reserva</Link>} />
    <form className="panel filters" onSubmit={aplicarFiltros} noValidate aria-label="Filtros de reservas">
      {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
      <div className="form-grid">
        <Campo nombre="customer" etiqueta="Cliente" ayuda="Busca por nombre o correo de la reserva."><input id="customer" name="customer" maxLength={254} value={cliente} onChange={(evento) => establecerCliente(evento.target.value)} /></Campo>
        <Campo nombre="customer_user_id" etiqueta="ID de cuenta" ayuda="Opcional. Filtra por propietario de cuenta, sin asociar históricos por correo." error={retroalimentacionFormulario.errores.customer_user_id}><input id="customer_user_id" name="customer_user_id" inputMode="numeric" value={idUsuarioCliente} onChange={(evento) => establecerIdUsuarioCliente(evento.target.value)} /></Campo>
        <Campo nombre="equipment_id" etiqueta="Equipo">
          <select id="equipment_id" name="equipment_id" value={idEquipo} onChange={(evento) => { establecerIdEquipo(evento.target.value); }} disabled={equipo.cargando}>
            <option value="">Todos los equipos</option>
            {equipo.datos?.map((elementoLista) => <option key={elementoLista.id} value={elementoLista.id}>{elementoLista.code} · {elementoLista.name}{elementoLista.active ? '' : ' (inactivo)'}</option>)}
          </select>
        </Campo>
        <Campo nombre="origin" etiqueta="Origen"><select id="origin" name="origin" value={origen} onChange={(evento) => establecerOrigen(evento.target.value as OrigenReserva | '')}><option value="">Todos los orígenes</option>{Object.entries(origenesReserva).map(([valor, etiqueta]) => <option key={valor} value={valor}>{etiqueta}</option>)}</select></Campo>
        <Campo nombre="status" etiqueta="Estado">
          <select id="status" name="status" value={estado} onChange={(evento) => { establecerEstado(evento.target.value as EstadoReserva | ''); }}>
            <option value="">Todos los estados</option>
            <option value="confirmed">Confirmada</option>
            <option value="cancelled">Cancelada</option>
          </select>
        </Campo>
        <Campo nombre="start_date" etiqueta="Desde" error={retroalimentacionFormulario.errores.start_date}>
          <input id="start_date" name="start_date" type="date" value={fechaInicio} onChange={(evento) => { establecerFechaInicio(evento.target.value); }} />
        </Campo>
        <Campo nombre="end_date" etiqueta="Hasta" error={retroalimentacionFormulario.errores.end_date}>
          <input id="end_date" name="end_date" type="date" value={fechaFin} onChange={(evento) => { establecerFechaFin(evento.target.value); }} />
        </Campo>
      </div>
      <p className="text-muted">Las fechas seleccionan reservas que solapan el intervalo; el día final queda excluido.</p>
      <div className="form-actions">
        <button className="button button-secondary" type="submit">Aplicar filtros</button>
        <button className="button button-secondary" type="button" onClick={restablecerFiltros}>Limpiar filtros</button>
      </div>
    </form>
    {equipo.error && <Aviso tono="error">{equipo.error} <button className="button button-secondary" type="button" onClick={equipo.recargar}>Reintentar equipos</button></Aviso>}
    {reservas.cargando && <p role="status">Cargando reservas…</p>}
    {reservas.error && <Aviso tono="error">{reservas.error} <button className="button button-secondary" type="button" onClick={reservas.recargar}>Reintentar</button></Aviso>}
    {!reservas.cargando && !reservas.error && reservas.datos && (reservas.datos.length === 0
      ? <EstadoVacio titulo="No hay reservas con estos filtros" descripcion="Prueba otro equipo o intervalo, o registra una nueva reserva." />
      : <section className="panel" aria-label="Listado de reservas">
        <div className="panel-header"><p className="text-muted">{reservas.datos.length} reservas encontradas</p></div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table>
          <caption className="sr-only">Reservas y estado actual</caption>
          <thead><tr><th scope="col">Reserva / cliente</th><th scope="col">Propietario y origen</th><th scope="col">Equipo</th><th scope="col">Intervalo</th><th scope="col">Estado</th><th scope="col">Acción</th></tr></thead>
          <tbody>{reservas.datos.map((reserva) => {
            const unidad = equipo.datos?.find((elementoLista) => elementoLista.id === reserva.equipment_id);
            return <tr key={reserva.id}>
              <td><span className="cell-title">#{reserva.id} · {reserva.customer_name}</span><span className="cell-subtitle">{reserva.customer_email}</span></td>
              <td><span className="cell-title">{titularReserva(reserva)}</span><span className="cell-subtitle">{origenReserva(reserva)}</span></td>
              <td><Link to={`/admin/equipos/${reserva.equipment_id}`}>{unidad?.code ?? `Equipo #${reserva.equipment_id}`}</Link><span className="cell-subtitle">{unidad?.name}</span></td>
              <td><span className="cell-title">{formatearFecha(reserva.start_date)} → {formatearFecha(reserva.end_date)}</span><span className="cell-subtitle">Fin excluido</span></td>
              <td><EtiquetaEstado clase={reserva.status} /></td>
              <td><Link to={`/admin/reservas/${reserva.id}`} aria-label={`Ver reserva #${reserva.id}`}>Ver detalle</Link></td>
            </tr>;
          })}</tbody>
        </table></div>
      </section>)}
  </>;
}
