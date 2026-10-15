import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, type PrioridadIncidencia } from '../api/cliente';
import { EstadoVacio, Campo, Aviso, CabeceraPagina } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useEstaMontado } from '../hooks/useEstaMontado';
import { useRecurso } from '../hooks/useRecurso';

export default function PaginaFormularioIncidencia() {
  const [busqueda] = useSearchParams();
  const navegar = useNavigate();
  const estaMontado = useEstaMontado();
  const [idEquipo, establecerIdEquipo] = useState(busqueda.get('equipment_id') ?? '');
  const [titulo, establecerTitulo] = useState('');
  const [descripcion, establecerDescripcion] = useState('');
  const [prioridad, establecerPrioridad] = useState<PrioridadIncidencia>('medium');
  const [bloqueante, establecerBloqueante] = useState(false);
  const [confirmando, establecerConfirmando] = useState(false);
  const botonConfirmar = useRef<HTMLButtonElement>(null);
  const botonEnviar = useRef<HTMLButtonElement>(null);
  const cargar = useCallback(() => api.listarEquipos(), []);
  const { datos: equipo, cargando, error, recargar } = useRecurso(cargar);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();

  useEffect(() => { if (confirmando) botonConfirmar.current?.focus(); }, [confirmando]);

  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (retroalimentacionFormulario.pendiente) return;
    retroalimentacionFormulario.limpiar();
    const errores: Record<string, string> = {};
    if (!idEquipo) errores.equipment_id = 'Selecciona un equipo.';
    if (!titulo.trim()) errores.title = 'Escribe un título para la incidencia.';
    if (Object.keys(errores).length > 0) { retroalimentacionFormulario.establecerValidacion(errores); return; }
    if (bloqueante) establecerConfirmando(true);
    else void crear();
  }

  async function crear() {
    if (retroalimentacionFormulario.pendiente) return;
    retroalimentacionFormulario.limpiar();
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      const incidencia = await api.crearIncidencia({ equipment_id: Number(idEquipo), title: titulo, description: descripcion, priority: prioridad, blocking: bloqueante });
      if (!estaMontado()) return;
      navegar(`/admin/incidencias/${incidencia.id}`, { state: { success: 'Incidencia registrada.' } });
    } catch (fallo: unknown) {
      if (estaMontado()) retroalimentacionFormulario.establecerFallo(fallo);
    } finally {
      if (estaMontado()) retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  return <>
    <Link className="back-link" to="/admin/incidencias">Volver a incidencias</Link>
    <CabeceraPagina titulo="Registrar incidencia" descripcion="Registra una incidencia interna vinculada a una unidad física. Los avisos del cliente se crean desde su reserva." />
    {cargando && <p role="status">Cargando equipos…</p>}
    {error && <Aviso tono="error">{error} <button className="button button-secondary" type="button" onClick={recargar}>Volver a cargar</button></Aviso>}
    {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
    {equipo?.length === 0 ? <EstadoVacio titulo="Primero necesitas un equipo" descripcion="Registra una unidad para poder asociarle incidencias."
      accion={<Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link>} /> : equipo && <form className="panel stack" onSubmit={enviar} noValidate aria-busy={retroalimentacionFormulario.pendiente}>
      <fieldset className="stack admin-incident-fields" disabled={retroalimentacionFormulario.pendiente || confirmando}>
        <legend>Datos de la incidencia interna</legend>
      <div className="form-grid">
        <Campo nombre="equipment_id" etiqueta="Equipo" error={retroalimentacionFormulario.errores.equipment_id} ayuda="También puedes registrar problemas de equipos inactivos."><select id="equipment_id" required value={idEquipo} onChange={(evento) => establecerIdEquipo(evento.target.value)}>
          <option value="">Selecciona un equipo</option>{equipo.map((elementoLista) => <option key={elementoLista.id} value={elementoLista.id}>{elementoLista.code} · {elementoLista.name}{elementoLista.active ? '' : ' (inactivo)'}</option>)}
        </select></Campo>
        <Campo nombre="priority" etiqueta="Prioridad" error={retroalimentacionFormulario.errores.priority}><select id="priority" value={prioridad} onChange={(evento) => establecerPrioridad(evento.target.value as PrioridadIncidencia)}>
          <option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option>
        </select></Campo>
      </div>
      <Campo nombre="title" etiqueta="Título" error={retroalimentacionFormulario.errores.title}><input id="title" required maxLength={160} value={titulo} onChange={(evento) => establecerTitulo(evento.target.value)} /></Campo>
      <Campo nombre="description" etiqueta="Descripción" error={retroalimentacionFormulario.errores.description}><textarea id="description" maxLength={2000} rows={4} value={descripcion} onChange={(evento) => establecerDescripcion(evento.target.value)} /></Campo>
      <div className="checkbox-field"><input id="blocking" type="checkbox" checked={bloqueante} aria-invalid={Boolean(retroalimentacionFormulario.errores.blocking)} aria-describedby={retroalimentacionFormulario.errores.blocking ? 'blocking-hint blocking-error' : 'blocking-hint'} onChange={(evento) => establecerBloqueante(evento.target.checked)} /><label htmlFor="blocking">Bloquea nuevas reservas</label></div>
      <p id="blocking-hint" className="text-muted">Una incidencia bloqueante sin resolver impide nuevas reservas. Las reservas existentes se conservan. La prioridad por sí sola no bloquea.</p>
      {retroalimentacionFormulario.errores.blocking && <p id="blocking-error" className="field-error">{retroalimentacionFormulario.errores.blocking}</p>}
      </fieldset>
      {confirmando ? <fieldset className="stack confirmation"><legend>Confirmar bloqueo del equipo</legend><p>Se rechazarán nuevas reservas de este equipo hasta resolver o retirar el bloqueo. Las reservas confirmadas no se cancelan automáticamente.</p><div className="inline-actions"><button ref={botonConfirmar} className="button button-danger" type="button" disabled={retroalimentacionFormulario.pendiente} onClick={() => { void crear(); }}>{retroalimentacionFormulario.pendiente ? 'Registrando…' : 'Sí, registrar y bloquear'}</button><button className="button button-secondary" type="button" disabled={retroalimentacionFormulario.pendiente} onClick={() => { establecerConfirmando(false); queueMicrotask(() => botonEnviar.current?.focus()); }}>Volver a editar</button></div></fieldset> : <div className="form-actions"><button ref={botonEnviar} className="button" type="submit" disabled={retroalimentacionFormulario.pendiente}>{retroalimentacionFormulario.pendiente ? 'Registrando…' : 'Registrar incidencia'}</button><Link className="button button-secondary" to="/admin/incidencias">Cancelar</Link></div>}
    </form>}
  </>;
}
