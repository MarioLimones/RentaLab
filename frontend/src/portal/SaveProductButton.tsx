import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { accessUrl } from '../auth/destinations';
import { useSavedProducts } from './savedProductsContext';
import './saved-products.css';

function Heart({ filled }: { filled: boolean }) {
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" /></svg>;
}

export function SaveProductButton({ id, name }: { id: number; name: string }) {
  const list = useSavedProducts();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const saved = list.ids.includes(id);
  if (list.admin) return null;
  if (!list.customer) return <Link className="save-product-button" to={accessUrl(location.pathname + location.search)} aria-label={`Acceder para guardar ${name} en mi lista`}><Heart filled={false} /><span>Guardar en mi lista</span></Link>;
  return <div className="save-product-control">
    <button type="button" className={`save-product-button${saved ? ' is-saved' : ''}`} aria-pressed={saved} aria-label={`${saved ? 'Quitar' : 'Guardar'} ${name} ${saved ? 'de' : 'en'} mi lista`} disabled={list.checking || list.loading || list.pending || !!list.error} onClick={() => {
      setError(null); setUpdating(true);
      void list.change(id, !saved).catch((failure: unknown) => setError(failure instanceof Error ? failure.message : 'No se pudo actualizar tu lista.')).finally(() => setUpdating(false));
    }}><Heart filled={saved} /><span>{updating ? 'Guardando…' : list.loading ? 'Cargando lista…' : saved ? 'En mi lista' : 'Guardar en mi lista'}</span></button>
    {error && <p className="field-error" role="alert">{error}</p>}
    {list.error && <button className="saved-list-retry" type="button" disabled={list.pending} onClick={list.reload}>Reintentar cargar mi lista</button>}
  </div>;
}
