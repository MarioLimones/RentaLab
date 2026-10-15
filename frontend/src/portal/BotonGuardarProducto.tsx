import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { urlAcceso } from '../autenticacion/destinos';
import { useProductosGuardados } from './contextoProductosGuardados';
import './productos-guardados.css';

function Corazon({ rellenado }: { rellenado: boolean }) {
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill={rellenado ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" /></svg>;
}

export function BotonGuardarProducto({ id, nombre }: { id: number; nombre: string }) {
  const lista = useProductosGuardados();
  const ubicacion = useLocation();
  const [error, establecerError] = useState<string | null>(null);
  const [actualizando, establecerActualizando] = useState(false);
  const guardado = lista.ids.includes(id);
  if (lista.administracion) return null;
  if (!lista.cliente) return <Link className="save-product-button" to={urlAcceso(ubicacion.pathname + ubicacion.search)} aria-label={`Acceder para guardar ${nombre} en mi lista`}><Corazon rellenado={false} /><span>Guardar en mi lista</span></Link>;
  return <div className="save-product-control">
    <button type="button" className={`save-product-button${guardado ? ' is-saved' : ''}`} aria-pressed={guardado} aria-label={`${guardado ? 'Quitar' : 'Guardar'} ${nombre} ${guardado ? 'de' : 'en'} mi lista`} disabled={lista.comprobando || lista.cargando || lista.pendiente || !!lista.error} onClick={() => {
      establecerError(null); establecerActualizando(true);
      void lista.cambio(id, !guardado).catch((fallo: unknown) => establecerError(fallo instanceof Error ? fallo.message : 'No se pudo actualizar tu lista.')).finally(() => establecerActualizando(false));
    }}><Corazon rellenado={guardado} /><span>{actualizando ? 'Guardando…' : lista.cargando ? 'Cargando lista…' : guardado ? 'En mi lista' : 'Guardar en mi lista'}</span></button>
    {error && <p className="field-error" role="alert">{error}</p>}
    {lista.error && <button className="saved-list-retry" type="button" disabled={lista.pendiente} onClick={lista.recargar}>Reintentar cargar mi lista</button>}
  </div>;
}
