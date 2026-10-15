import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Equipo, type EntradaEquipo } from '../api/cliente';
import { Campo, Aviso, CabeceraPagina } from '../componentes/interfaz';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';
import { useEstaMontado } from '../hooks/useEstaMontado';
import { useRecurso } from '../hooks/useRecurso';

const equiposVacios: EntradaEquipo = { code: '', name: '', category: '', description: '', public_description: '', technical_specs: {}, image_url: null, active: true };

interface FilaEspecificacionTecnica { id: number; nombre: string; valor: string; }

function urlImagenValida(valor: string): boolean {
  if ([...valor].some((caracter) => caracter === '\\' || caracter.charCodeAt(0) <= 32 || caracter.charCodeAt(0) === 127)) return false;
  if (valor.startsWith('/api/public/images/')) return /^\/api\/public\/images\/[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:\/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$/.test(valor);
  if (!/^https:\/\//i.test(valor)) return false;
  try {
    const url = new URL(valor);
    return url.protocol === 'https:' && Boolean(url.hostname) && !url.username && !url.password && !url.search && !url.hash;
  } catch { return false; }
}

function EditorEquipo({ inicial, idEquipo }: { inicial: EntradaEquipo; idEquipo?: number }) {
  const [valores, establecerValores] = useState<EntradaEquipo>(inicial);
  const [especificaciones, establecerEspecificaciones] = useState<FilaEspecificacionTecnica[]>(() => Object.entries(inicial.technical_specs ?? {}).map(([nombre, valor], id): FilaEspecificacionTecnica => ({ id, nombre, valor })));
  const idEspecificacionSiguiente = useRef(especificaciones.length);
  const destinoEnfoque = useRef<string | null>(null);
  const enviandoFormulario = useRef(false);
  const navegar = useNavigate();
  const estaMontado = useEstaMontado();
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  const editando = idEquipo !== undefined;

  useEffect(() => {
    if (destinoEnfoque.current) {
      document.getElementById(destinoEnfoque.current)?.focus();
      destinoEnfoque.current = null;
    }
  }, [especificaciones]);

  function anadirEspecificacion() {
    if (especificaciones.length >= 20 || retroalimentacionFormulario.pendiente) return;
    const id = idEspecificacionSiguiente.current++;
    destinoEnfoque.current = `technical_specs-${id}-name`;
    establecerEspecificaciones([...especificaciones, { id, nombre: '', valor: '' }]);
  }

  function eliminarEspecificacion(id: number) {
    const indice = especificaciones.findIndex((especificacion) => especificacion.id === id);
    const siguiente = especificaciones[indice + 1] ?? especificaciones[indice - 1];
    destinoEnfoque.current = siguiente ? `technical_specs-${siguiente.id}-name` : 'add-technical-spec';
    establecerEspecificaciones(especificaciones.filter((especificacion) => especificacion.id !== id));
    retroalimentacionFormulario.limpiar();
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enviandoFormulario.current) return;
    retroalimentacionFormulario.limpiar();
    const errores: Record<string, string> = {};
    if (!valores.code.trim()) errores.code = 'Introduce el código de la unidad.';
    if (!valores.name.trim()) errores.name = 'Introduce el nombre del equipo.';
    if (!valores.category.trim()) errores.category = 'Introduce una categoría.';
    const nombres = new Set<string>();
    for (const especificacion of especificaciones) {
      const nombre = especificacion.nombre.trim();
      if (!nombre) errores[`technical_specs-${especificacion.id}-name`] = 'Introduce el nombre o elimina esta característica.';
      else if (nombres.has(nombre)) errores[`technical_specs-${especificacion.id}-name`] = 'Cada característica debe tener un nombre diferente.';
      else nombres.add(nombre);
      if (!especificacion.valor.trim()) errores[`technical_specs-${especificacion.id}-value`] = 'Introduce el valor de esta característica.';
    }
    const urlImagen = valores.image_url?.trim() ?? '';
    if (urlImagen && !urlImagenValida(urlImagen)) errores.image_url = 'Usa una URL HTTPS sin credenciales, consulta ni fragmento, o una ruta /api/public/images/... válida.';
    if (Object.keys(errores).length > 0) {
      retroalimentacionFormulario.establecerValidacion(errores);
      return;
    }
    enviandoFormulario.current = true;
    retroalimentacionFormulario.establecerPendiente(true);
    try {
      const entrada: EntradaEquipo = { ...valores, public_description: valores.public_description ?? '', technical_specs: Object.fromEntries(especificaciones.map((especificacion) => [especificacion.nombre.trim(), especificacion.valor.trim()])), image_url: urlImagen || null };
      const guardado = editando ? await api.modificarEquipo(idEquipo, entrada) : await api.crearEquipo(entrada);
      if (!estaMontado()) return;
      navegar(`/admin/equipos/${guardado.id}`, { state: { notice: editando ? 'Equipo actualizado correctamente.' : 'Equipo creado correctamente.' } });
    } catch (fallo) {
      if (estaMontado()) retroalimentacionFormulario.establecerFallo(fallo);
    } finally {
      enviandoFormulario.current = false;
      if (estaMontado()) retroalimentacionFormulario.establecerPendiente(false);
    }
  }

  return <>
    <Link className="back-link" to={editando ? `/admin/equipos/${idEquipo}` : '/admin/equipos'}>← {editando ? 'Volver al equipo' : 'Volver a equipos'}</Link>
    <CabeceraPagina titulo={editando ? 'Editar equipo' : 'Crear equipo'} descripcion="Registra una unidad física. El servidor normaliza su código y comprueba que sea único." />
    {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
    <form className="panel" onSubmit={(evento) => { void enviar(evento); }} noValidate aria-busy={retroalimentacionFormulario.pendiente}>
      <div className="form-grid">
        <fieldset className="full-width" disabled={retroalimentacionFormulario.pendiente}><legend>Datos de gestión</legend><div className="form-grid">
        <Campo nombre="code" etiqueta="Código" error={retroalimentacionFormulario.errores.code} ayuda="Único por unidad. Letras, números, guion o guion bajo; hasta 40 caracteres.">
          <input id="code" name="code" required maxLength={40} autoComplete="off" value={valores.code} onChange={(evento) => establecerValores({ ...valores, code: evento.target.value })} aria-invalid={Boolean(retroalimentacionFormulario.errores.code)} />
        </Campo>
        <Campo nombre="name" etiqueta="Nombre" error={retroalimentacionFormulario.errores.name}><input id="name" name="name" required maxLength={120} value={valores.name} onChange={(evento) => establecerValores({ ...valores, name: evento.target.value })} aria-invalid={Boolean(retroalimentacionFormulario.errores.name)} /></Campo>
        <Campo nombre="category" etiqueta="Categoría" error={retroalimentacionFormulario.errores.category}><input id="category" name="category" required maxLength={80} placeholder="Por ejemplo, Cámaras" value={valores.category} onChange={(evento) => establecerValores({ ...valores, category: evento.target.value })} aria-invalid={Boolean(retroalimentacionFormulario.errores.category)} /></Campo>
        <Campo nombre="description" etiqueta="Descripción interna (opcional)" error={retroalimentacionFormulario.errores.description} ayuda="Solo administración. Hasta 2000 caracteres."><textarea id="description" name="description" rows={4} maxLength={2000} value={valores.description} onChange={(evento) => establecerValores({ ...valores, description: evento.target.value })} aria-invalid={Boolean(retroalimentacionFormulario.errores.description)} /></Campo>
        </div></fieldset>
        <fieldset className="full-width" disabled={retroalimentacionFormulario.pendiente}><legend>Ficha pública del catálogo</legend><div className="form-grid">
          <Campo nombre="public_description" etiqueta="Descripción pública (opcional)" error={retroalimentacionFormulario.errores.public_description} ayuda="Visible para visitantes y clientes. Hasta 2000 caracteres."><textarea name="public_description" rows={4} maxLength={2000} value={valores.public_description ?? ''} onChange={(evento) => establecerValores({ ...valores, public_description: evento.target.value })} /></Campo>
          <Campo nombre="image_url" etiqueta="Imagen (opcional)" error={retroalimentacionFormulario.errores.image_url} ayuda="URL HTTPS o ruta /api/public/images/... sin consulta ni fragmento. Al dejarla vacía se muestra la alternativa local."><input name="image_url" type="text" inputMode="url" maxLength={2048} autoComplete="off" value={valores.image_url ?? ''} onChange={(evento) => establecerValores({ ...valores, image_url: evento.target.value })} /></Campo>
          <fieldset id="technical_specs" tabIndex={-1} className="full-width" aria-describedby={`technical-specs-hint${retroalimentacionFormulario.errores.technical_specs ? ' technical_specs-error' : ''}`}><legend>Características técnicas</legend>
            <p className="field-hint" id="technical-specs-hint">Hasta 20 características. Nombre único de hasta 80 caracteres y valor de hasta 300. No incluyas notas internas.</p>
            {retroalimentacionFormulario.errores.technical_specs && <p className="field-error" id="technical_specs-error">{retroalimentacionFormulario.errores.technical_specs}</p>}
            <div className="detail-grid">{especificaciones.map((especificacion, indice) => <fieldset key={especificacion.id}><legend>Característica {indice + 1}</legend><div className="form-grid">
              <Campo nombre={`technical_specs-${especificacion.id}-name`} etiqueta={`Nombre de característica ${indice + 1}`} error={retroalimentacionFormulario.errores[`technical_specs-${especificacion.id}-name`]}><input required maxLength={80} value={especificacion.nombre} onChange={(evento) => establecerEspecificaciones(especificaciones.map((fila) => fila.id === especificacion.id ? { ...fila, nombre: evento.target.value } : fila))} /></Campo>
              <Campo nombre={`technical_specs-${especificacion.id}-value`} etiqueta={`Valor de característica ${indice + 1}`} error={retroalimentacionFormulario.errores[`technical_specs-${especificacion.id}-value`]}><input required maxLength={300} value={especificacion.valor} onChange={(evento) => establecerEspecificaciones(especificaciones.map((fila) => fila.id === especificacion.id ? { ...fila, valor: evento.target.value } : fila))} /></Campo>
              <div className="full-width"><button className="button button-secondary" type="button" onClick={() => eliminarEspecificacion(especificacion.id)} aria-label={`Eliminar característica ${indice + 1}`}>Eliminar característica</button></div>
            </div></fieldset>)}</div>
            <div className="form-actions"><button id="add-technical-spec" className="button button-secondary" type="button" disabled={especificaciones.length >= 20} onClick={anadirEspecificacion}>Añadir característica</button><span className="text-muted" role="status">{especificaciones.length} de 20 características</span></div>
          </fieldset>
        </div></fieldset>
      </div>
      <label className="checkbox-label"><input type="checkbox" disabled={retroalimentacionFormulario.pendiente} checked={valores.active} onChange={(evento) => establecerValores({ ...valores, active: evento.target.checked })} />Equipo activo para nuevas reservas y catálogo público</label>
      <div className="form-actions"><button className="button" type="submit" disabled={retroalimentacionFormulario.pendiente}>{retroalimentacionFormulario.pendiente ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear equipo'}</button><Link className="button button-secondary" to={editando ? `/admin/equipos/${idEquipo}` : '/admin/equipos'}>Cancelar</Link></div>
    </form>
  </>;
}

function EditorEquipoExistente({ idEquipo }: { idEquipo: number }) {
  const cargar = useCallback(() => api.obtenerEquipo(idEquipo), [idEquipo]);
  const { datos, cargando, error, recargar } = useRecurso<Equipo>(cargar);
  if (cargando) return <p role="status">Cargando equipo…</p>;
  if (error) return <><CabeceraPagina titulo="Editar equipo" /><Aviso tono="error">{error} <button type="button" className="button button-secondary" onClick={recargar}>Volver a cargar</button></Aviso><Link to="/admin/equipos">Volver a equipos</Link></>;
  if (!datos) return null;
  const { code: codigo, name: nombre, category: categoria, description: descripcion, public_description: descripcion_publica, technical_specs: especificaciones_tecnicas, image_url: url_imagen, active: activo } = datos;
  return <EditorEquipo key={datos.id} idEquipo={datos.id} inicial={{ code: codigo, name: nombre, category: categoria, description: descripcion, public_description: descripcion_publica ?? '', technical_specs: especificaciones_tecnicas ?? {}, image_url: url_imagen ?? null, active: activo }} />;
}

export function PaginaFormularioEquipo() {
  const { id } = useParams();
  if (id === undefined) return <EditorEquipo inicial={equiposVacios} />;
  const idEquipo = Number(id);
  if (!Number.isSafeInteger(idEquipo) || idEquipo <= 0) return <><CabeceraPagina titulo="Equipo no válido" /><Aviso tono="error">El identificador del equipo no es válido.</Aviso><Link to="/admin/equipos">Volver a equipos</Link></>;
  return <EditorEquipoExistente key={idEquipo} idEquipo={idEquipo} />;
}
