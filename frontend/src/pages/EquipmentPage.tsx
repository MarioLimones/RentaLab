import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Equipment } from '../api/client';
import { EmptyState, Notice, PageHeader, StatusBadge } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { useFormFeedback } from '../hooks/useFormFeedback';

export function EquipmentPage() {
  const load = useCallback(() => api.listEquipment(), []);
  const { data, loading, error, reload } = useResource(load);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [changingId, setChangingId] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [persisted, setPersisted] = useState<{ source: Equipment[] | null; updates: Map<number, Equipment> } | null>(null);
  const feedback = useFormFeedback();
  // Keep successful writes visible if refreshing the list fails. A new list
  // response replaces the snapshot and becomes the current source of truth.
  const equipment = (data ?? []).map((item) => persisted?.source === data ? persisted.updates.get(item.id) ?? item : item);
  const categories = [...new Set(equipment.map((item) => item.category))].sort((a, b) => a.localeCompare(b, 'es'));
  const normalizedSearch = search.trim().toLocaleLowerCase('es');
  const filtered = equipment.filter((item) => {
    const matchesText = `${item.code} ${item.name} ${item.description}`.toLocaleLowerCase('es').includes(normalizedSearch);
    const matchesCategory = category === '' || item.category === category;
    const matchesStatus = status === '' || item.active === (status === 'active');
    return matchesText && matchesCategory && matchesStatus;
  });

  async function toggleActive(item: Equipment) {
    if (!data || loading || changingId !== null) return;
    feedback.clear();
    setSuccess(null);
    setChangingId(item.id);
    try {
      const updated = await api.patchEquipment(item.id, { active: !item.active });
      setPersisted((previous) => {
        const updates = previous?.source === data ? new Map(previous.updates) : new Map<number, Equipment>();
        updates.set(updated.id, updated);
        return { source: data, updates };
      });
      setSuccess(`${updated.name}: equipo ${updated.active ? 'activado' : 'desactivado'} correctamente.`);
      reload();
    } catch (failure) {
      feedback.setFailure(failure);
    } finally {
      setChangingId(null);
    }
  }

  return <>
    <PageHeader title="Equipos" description="Cada código identifica una unidad física del catálogo." action={<div className="inline-actions"><button className="button button-secondary" type="button" disabled={loading || changingId !== null} onClick={reload}>Actualizar datos</button><Link className="button" to="/admin/equipos/nuevo">Crear equipo</Link></div>} />
    {success && <Notice tone="success">{success}</Notice>}
    {feedback.message && <Notice tone="error" errors={feedback.errors}>{feedback.message}</Notice>}
    <section className="panel" aria-label="Catálogo de equipos">
      <div className="filters">
        <div className="field"><label htmlFor="equipment-search">Buscar equipos</label><input id="equipment-search" type="search" placeholder="Código, nombre o descripción" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-category">Categoría</label><select id="equipment-category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Todas las categorías</option>{categories.map((value) => <option key={value}>{value}</option>)}</select></div>
        <div className="field"><label htmlFor="equipment-status">Estado</label><select id="equipment-status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos los estados</option><option value="active">Activos</option><option value="inactive">Inactivos</option></select></div>
      </div>
      {loading && <p role="status">Cargando equipos…</p>}
      {error && <Notice tone="error">{error} <button className="button button-secondary" type="button" onClick={reload}>Volver a cargar</button></Notice>}
      {data && (filtered.length > 0 ? <>
        <p className="text-muted">{filtered.length} de {equipment.length} unidades</p>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable horizontalmente"><table><caption className="sr-only">Unidades físicas del catálogo</caption><thead><tr><th scope="col">Equipo</th><th scope="col">Categoría</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead><tbody>
          {filtered.map((item) => <tr key={item.id}>
            <td><Link className="cell-title" to={`/admin/equipos/${item.id}`}>{item.name}</Link><span className="cell-subtitle">{item.code}</span></td>
            <td>{item.category}</td><td><StatusBadge kind={item.active ? 'active' : 'inactive'} /></td>
            <td><div className="inline-actions"><Link to={`/admin/equipos/${item.id}/editar`}>Editar<span className="sr-only"> {item.name}</span></Link><button className="button button-secondary" type="button" disabled={changingId !== null || loading} aria-label={`${item.active ? 'Desactivar' : 'Activar'} ${item.name}`} onClick={() => { void toggleActive(item); }}>{changingId === item.id ? 'Guardando…' : item.active ? 'Desactivar' : 'Activar'}</button></div></td>
          </tr>)}
        </tbody></table></div>
      </> : <EmptyState title={equipment.length === 0 ? 'Todavía no hay equipos' : 'No hay equipos con estos filtros'} description={equipment.length === 0 ? 'Añade la primera unidad física para empezar a gestionar el material.' : 'Prueba otro texto, categoría o estado.'} action={equipment.length === 0 ? <Link className="button" to="/admin/equipos/nuevo">Crear primer equipo</Link> : <button type="button" className="button button-secondary" onClick={() => { setSearch(''); setCategory(''); setStatus(''); }}>Limpiar filtros</button>} />)}
    </section>
  </>;
}
