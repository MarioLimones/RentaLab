import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Equipo } from '../api/cliente';
import { EstadoVacio, Aviso, CabeceraPagina, EtiquetaEstado } from '../componentes/interfaz';
import { useRecurso } from '../hooks/useRecurso';
import { useRetroalimentacionFormulario } from '../hooks/useRetroalimentacionFormulario';

export function PaginaEquipos() {
  const cargar = useCallback(() => api.listarEquipos(), []);
  const { datos, cargando, error, recargar } = useRecurso(cargar);
  const [busqueda, establecerBusqueda] = useState('');
  const [categoria, establecerCategoria] = useState('');
  const [estado, establecerEstado] = useState('');
  const [idEnCambio, establecerIdEnCambio] = useState<number | null>(null);
  const [exito, establecerExito] = useState<string | null>(null);
  const [conservado, establecerConservado] = useState<{ fuente: Equipo[] | null; actualizaciones: Map<number, Equipo> } | null>(null);
  const retroalimentacionFormulario = useRetroalimentacionFormulario();
  // Mantén visibles las escrituras completadas si falla la actualización de la lista. Una nueva
  // respuesta sustituye la instantánea y pasa a ser la fuente de datos vigente.
  const equipo = (datos ?? []).map((elementoLista) => conservado?.fuente === datos ? conservado.actualizaciones.get(elementoLista.id) ?? elementoLista : elementoLista);
  const categorias = [...new Set(equipo.map((elementoLista) => elementoLista.category))].sort((a, b) => a.localeCompare(b, 'es'));
  const busquedaNormalizada = busqueda.trim().toLocaleLowerCase('es');
  const filtrados = equipo.filter((elementoLista) => {
    const coincideTexto = `${elementoLista.code} ${elementoLista.name} ${elementoLista.description}`.toLocaleLowerCase('es').includes(busquedaNormalizada);
    const coincideCategoria = categoria === '' || elementoLista.category === categoria;
    const coincideEstado = estado === '' || elementoLista.active === (estado === 'active');
    return coincideTexto && coincideCategoria && coincideEstado;
  });

  async function alternarActivo(elementoLista: Equipo) {
    if (!datos || cargando || idEnCambio !== null) return;
    retroalimentacionFormulario.limpiar();
    establecerExito(null);
    establecerIdEnCambio(elementoLista.id);
    try {
      const actualizado = await api.modificarEquipo(elementoLista.id, { active: !elementoLista.active });
      establecerConservado((anterior) => {
        const actualizaciones = anterior?.fuente === datos ? new Map(anterior.actualizaciones) : new Map<number, Equipo>();
        actualizaciones.set(actualizado.id, actualizado);
        return { fuente: datos, actualizaciones };
      });
      establecerExito(`${actualizado.name}: equipo ${actualizado.active ? 'activado' : 'desactivado'} correctamente.`);
      recargar();
    } catch (fallo) {
      retroalimentacionFormulario.establecerFallo(fallo);
    } finally {
      establecerIdEnCambio(null);
    }
  }

  return <>
    <CabeceraPagina titulo="Equipos" descripcion="Cada código identifica una unidad física del catálogo." accion={<div className="inline-actions"><button className="button button-secondary" type="button" disabled={cargando || idEnCambio !== null} onClick={recargar}>Actualizar datos</button><Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link></div>} />
    {exito && <Aviso tono="success">{exito}</Aviso>}
    {retroalimentacionFormulario.mensaje && <Aviso tono="error" errores={retroalimentacionFormulario.errores}>{retroalimentacionFormulario.mensaje}</Aviso>}
    <section className="panel" aria-label="Catálogo de equipos">
      <div className="filters">
        <div className="field"><label htmlFor="equipment-search">Buscar equipos</label><input id="equipment-search" type="search" placeholder="Código, nombre o descripción" value={busqueda} onChange={(evento) => establecerBusqueda(evento.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-category">Categoría</label><select id="equipment-category" value={categoria} onChange={(evento) => establecerCategoria(evento.target.value)}><option value="">Todas las categorías</option>{categorias.map((valor) => <option key={valor}>{valor}</option>)}</select></div>
        <div className="field"><label htmlFor="equipment-status">Estado</label><select id="equipment-status" value={estado} onChange={(evento) => establecerEstado(evento.target.value)}><option value="">Todos los estados</option><option value="active">Activos</option><option value="inactive">Inactivos</option></select></div>
      </div>
      {cargando && <p role="status">Cargando equipos…</p>}
      {error && <Aviso tono="error">{error} <button className="button button-secondary" type="button" onClick={recargar}>Volver a cargar</button></Aviso>}
      {datos && (filtrados.length > 0 ? <>
        <p className="text-muted">{filtrados.length} de {equipo.length} unidades</p>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table><caption className="sr-only">Unidades físicas del catálogo</caption><thead><tr><th scope="col">Equipo</th><th scope="col">Categoría</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead><tbody>
          {filtrados.map((elementoLista) => <tr key={elementoLista.id}>
            <td><Link className="cell-title" to={`/admin/equipos/${elementoLista.id}`}>{elementoLista.name}</Link><span className="cell-subtitle">{elementoLista.code}</span></td>
            <td>{elementoLista.category}</td><td><EtiquetaEstado clase={elementoLista.active ? 'active' : 'inactive'} /></td>
            <td><div className="inline-actions"><Link to={`/admin/equipos/${elementoLista.id}/editar`}>Editar<span className="sr-only"> {elementoLista.name}</span></Link><button className="button button-secondary" type="button" disabled={idEnCambio !== null || cargando} aria-label={`${elementoLista.active ? 'Desactivar' : 'Activar'} ${elementoLista.name}`} onClick={() => { void alternarActivo(elementoLista); }}>{idEnCambio === elementoLista.id ? 'Guardando…' : elementoLista.active ? 'Desactivar' : 'Activar'}</button></div></td>
          </tr>)}
        </tbody></table></div>
      </> : <EstadoVacio titulo={equipo.length === 0 ? 'Todavía no hay equipos' : 'No hay equipos con estos filtros'} descripcion={equipo.length === 0 ? 'Añade la primera unidad física para empezar a gestionar el material.' : 'Prueba otro texto, categoría o estado.'} accion={equipo.length === 0 ? <Link className="button" to="/admin/equipos/nuevo">Crear primer equipo</Link> : <button type="button" className="button button-secondary" onClick={() => { establecerBusqueda(''); establecerCategoria(''); establecerEstado(''); }}>Limpiar filtros</button>} />)}
    </section>
  </>;
}
