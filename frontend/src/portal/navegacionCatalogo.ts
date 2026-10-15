import { destinoCatalogoPermitido } from '../autenticacion/destinos';
import type { IntervaloFechas } from '../tipos/api';
import { busquedaIntervalo } from './intervaloFechas';

const CLAVE_POSICION = 'rentalab.catalogue-position.v1';
export interface RegresoCatalogo { path: string; top: number; }
let ultimaPosicion: RegresoCatalogo | null = null;

function posicion(valor: unknown): RegresoCatalogo | null {
  if (typeof valor !== 'object' || valor === null || !('path' in valor) || !('top' in valor)
    || typeof valor.path !== 'string' || typeof valor.top !== 'number'
    || !Number.isFinite(valor.top) || valor.top < 0 || valor.top > 10_000_000) return null;
  const ruta = destinoCatalogoPermitido(valor.path);
  return ruta ? { path: ruta, top: valor.top } : null;
}

function posicionGuardada(ruta: string): RegresoCatalogo {
  try { ultimaPosicion = posicion(JSON.parse(sessionStorage.getItem(CLAVE_POSICION) ?? 'null')); } catch { /* El almacenamiento puede no estar disponible. */ }
  return ultimaPosicion?.path === ruta ? ultimaPosicion : { path: ruta, top: 0 };
}

export function recordarPosicionCatalogo(ruta: string) {
  const rutaSegura = destinoCatalogoPermitido(ruta);
  if (!rutaSegura) return;
  ultimaPosicion = { path: rutaSegura, top: Math.max(0, window.scrollY) };
  try { sessionStorage.setItem(CLAVE_POSICION, JSON.stringify(ultimaPosicion)); } catch { /* Conserva en memoria la posición de esta navegación. */ }
}

export function rutaProductoCatalogo(id: number, intervalo: IntervaloFechas, rutaDelCatalogo: string): string {
  const consulta = new URLSearchParams(busquedaIntervalo(intervalo));
  const ruta = destinoCatalogoPermitido(rutaDelCatalogo);
  // Las URL simples o con fechas conservan su formato. Los demás filtros acompañan al enlace,
  // también cuando se abre en otra pestaña o pasa por la autenticación.
  if (ruta && ['q', 'category', 'available'].some((key) => new URL(ruta, 'https://rentalab.invalid').searchParams.has(key))) consulta.set('catalogue', ruta);
  return `/equipos/${id}${consulta.size ? `?${consulta}` : ''}`;
}

export function regresoCatalogoProducto(estadoInterno: unknown, parametro: string | null, alternativa: string): RegresoCatalogo {
  const desdeEstado = typeof estadoInterno === 'object' && estadoInterno !== null && 'catalogueReturn' in estadoInterno && typeof estadoInterno.catalogueReturn === 'string'
    ? destinoCatalogoPermitido(estadoInterno.catalogueReturn) : null;
  const fuente = desdeEstado ?? destinoCatalogoPermitido(parametro) ?? destinoCatalogoPermitido(alternativa) ?? '/catalogo';
  const consulta = new URL(fuente, 'https://rentalab.invalid').searchParams;
  const fechas = new URL(destinoCatalogoPermitido(alternativa) ?? '/catalogo', 'https://rentalab.invalid').searchParams;
  for (const campo of ['start_date', 'end_date']) {
    consulta.delete(campo);
    const valor = fechas.get(campo);
    if (valor) consulta.set(campo, valor);
  }
  const ruta = destinoCatalogoPermitido(`/catalogo${consulta.size ? `?${consulta}` : ''}`) ?? '/catalogo';
  return posicionGuardada(ruta);
}

export function destinoDesplazamientoCatalogo(ruta: string, estadoInterno: unknown, esHistorial: boolean): number | null {
  const rutaSegura = destinoCatalogoPermitido(ruta);
  if (!rutaSegura) return null;
  const explicito = typeof estadoInterno === 'object' && estadoInterno !== null && 'catalogueRestore' in estadoInterno ? posicion(estadoInterno.catalogueRestore) : null;
  if (explicito?.path === rutaSegura) return explicito.top;
  const anterior = esHistorial ? posicionGuardada(rutaSegura) : null;
  return anterior && anterior.top > 0 ? anterior.top : null;
}
