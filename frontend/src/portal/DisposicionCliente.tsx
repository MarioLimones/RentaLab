import { useEffect, useRef } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAutenticacion } from '../autenticacion/contexto';
import { destinoPermitido } from '../autenticacion/destinos';
import ControlSesion from '../componentes/ControlSesion';
import MarcaIdentidad from '../componentes/Marca';
import { ProveedorProductosGuardados } from './ProveedorProductosGuardados';
import { useProductosGuardados } from './contextoProductosGuardados';
import './portal.css';

export default function EstructuraCliente() {
  const { sesion, comprobando } = useAutenticacion();
  const identidad = sesion ? `${sesion.role}:${sesion.user?.id ?? sesion.username}` : 'public';
  return <ProveedorProductosGuardados key={identidad} cliente={sesion?.role === 'customer'} administracion={sesion?.role === 'admin'} comprobando={comprobando}><ContenidoEstructuraCliente /></ProveedorProductosGuardados>;
}

function ContenidoEstructuraCliente() {
  const { sesion, comprobando, errorComprobacion, comprobarSesion } = useAutenticacion();
  const productosGuardados = useProductosGuardados();
  const ubicacion = useLocation();
  const principal = useRef<HTMLElement>(null);
  const cabecera = useRef<HTMLElement>(null);
  useEffect(() => {
    const elemento = cabecera.current;
    if (!elemento) return;
    const resultados = ubicacion.pathname === '/catalogo' ? principal.current?.querySelector('#catalogue-results') : null;
    let marco: number | null = null;
    const actualizarVisibilidad = () => {
      const oculto = !!resultados && resultados.getBoundingClientRect().top <= elemento.offsetHeight;
      if (elemento.hasAttribute('data-catalogue-hidden') !== oculto) elemento.toggleAttribute('data-catalogue-hidden', oculto);
    };
    // La navegación de cuenta en varias líneas debe dejar espacio al contenido enfocado y los paneles fijos.
    const actualizarAltura = () => {
      document.documentElement.style.setProperty('--portal-header-height', `${elemento.offsetHeight}px`);
      actualizarVisibilidad();
    };
    const alDesplazar = () => {
      if (marco === null) marco = window.requestAnimationFrame(() => { marco = null; actualizarVisibilidad(); });
    };
    actualizarAltura();
    const observador = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(actualizarAltura);
    observador?.observe(elemento);
    if (principal.current) observador?.observe(principal.current);
    window.addEventListener('resize', actualizarAltura);
    if (resultados) window.addEventListener('scroll', alDesplazar, { passive: true });
    return () => {
      observador?.disconnect();
      window.removeEventListener('resize', actualizarAltura);
      window.removeEventListener('scroll', alDesplazar);
      if (marco !== null) window.cancelAnimationFrame(marco);
      elemento.removeAttribute('data-catalogue-hidden');
      document.documentElement.style.removeProperty('--portal-header-height');
    };
  }, [ubicacion.pathname]);
  useEffect(() => {
    const titulos: Record<string, string> = { '/catalogo': 'Catálogo', '/mi-lista': 'Mi lista', '/mis-reservas': 'Mis reservas', '/mis-incidencias': 'Mis avisos', '/mi-cuenta': 'Mi cuenta' };
    if (!['/acceso', '/registro'].includes(ubicacion.pathname)) document.title = `RentaLab · ${titulos[ubicacion.pathname] ?? (ubicacion.pathname.startsWith('/equipos/') ? 'Equipo' : ubicacion.pathname.startsWith('/mis-reservas/') ? 'Mi reserva' : 'Página no encontrada')}`;
    if (!['/acceso', '/registro'].includes(ubicacion.pathname)) principal.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [ubicacion.pathname]);
  const identidad = sesion ? `${sesion.role}:${sesion.user?.id ?? sesion.username}` : 'public';
  const destino = destinoPermitido(['/acceso', '/registro'].includes(ubicacion.pathname) ? new URLSearchParams(ubicacion.search).get('next') : ubicacion.pathname + ubicacion.search);
  const busquedaAcceso = destino ? `?next=${encodeURIComponent(destino)}` : '';
  return <div className="portal-shell">
    <a className="skip-link" href="#main-content">Saltar al contenido</a>
    <header className="portal-header" ref={cabecera}>
      <div className="portal-container portal-header-inner">
        <Link to="/catalogo" className="brand portal-brand" aria-label="RentaLab, catálogo"><MarcaIdentidad /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></Link>
        <nav aria-label="Catálogo y cuenta" className="portal-navigation">
          <NavLink to="/catalogo"><span className="portal-nav-label">Catálogo</span></NavLink>
          {sesion?.role !== 'admin' && <NavLink to="/mi-lista"><span className="portal-nav-label">Mi lista</span>{productosGuardados.cliente && !productosGuardados.cargando && !productosGuardados.error && <span className="saved-list-count" aria-label={`${productosGuardados.ids.length} equipos guardados`}>{productosGuardados.ids.length}</span>}</NavLink>}
          {sesion?.role === 'customer' && <><NavLink to="/mis-reservas"><span className="portal-nav-label">Mis reservas</span></NavLink><NavLink to="/mis-incidencias"><span className="portal-nav-label">Mis avisos</span></NavLink><NavLink to="/mi-cuenta"><span className="portal-nav-label">Mi cuenta</span></NavLink></>}
        </nav>
        <div className="portal-header-account">
          {comprobando ? <span className="text-muted" role="status">Comprobando cuenta…</span>
            : errorComprobacion ? <button type="button" className="button button-secondary" onClick={() => { void comprobarSesion(); }}>Comprobar cuenta</button>
              : sesion ? <>{sesion.role === 'admin' && <Link to="/admin" className="button button-secondary">Panel de administración</Link>}<ControlSesion mostrarIdentidad={false} /></>
                : <><Link to={'/acceso' + busquedaAcceso} className="portal-access">Acceder</Link><Link to={'/registro' + busquedaAcceso} className="button portal-register-link">Crear cuenta</Link></>}
        </div>
      </div>
    </header>
    <main className="portal-container portal-content" id="main-content" tabIndex={-1} ref={principal}>
      <div key={identidad} className="portal-route"><Outlet /></div>
    </main>
    <footer className="portal-footer"><div className="portal-container portal-footer-inner"><div><strong>RentaLab</strong><p>Material audiovisual para tu próximo proyecto.</p></div><div><Link to="/catalogo">Explorar el catálogo</Link><a href="/api/public/images/photo-credits.txt" target="_blank" rel="noopener noreferrer">Créditos de fotografías</a><span>Proyecto demostrativo. Empresa y datos ficticios.</span></div></div></footer>
  </div>;
}
