import { useEffect, useRef } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { allowedDestination } from '../auth/destinations';
import SessionControl from '../components/SessionControl';
import BrandMark from '../components/BrandMark';
import { SavedProductsProvider } from './SavedProductsProvider';
import { useSavedProducts } from './savedProductsContext';
import './portal.css';

export default function ClientLayout() {
  const { session, checking } = useAuth();
  const identity = session ? `${session.role}:${session.user?.id ?? session.username}` : 'public';
  return <SavedProductsProvider key={identity} customer={session?.role === 'customer'} admin={session?.role === 'admin'} checking={checking}><ClientLayoutContent /></SavedProductsProvider>;
}

function ClientLayoutContent() {
  const { session, checking, checkError, checkSession } = useAuth();
  const savedProducts = useSavedProducts();
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  const header = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = header.current;
    if (!element) return;
    const results = location.pathname === '/catalogo' ? main.current?.querySelector('#catalogue-results') : null;
    let frame: number | null = null;
    const updateVisibility = () => {
      const hidden = !!results && results.getBoundingClientRect().top <= element.offsetHeight;
      if (element.hasAttribute('data-catalogue-hidden') !== hidden) element.toggleAttribute('data-catalogue-hidden', hidden);
    };
    // Wrapped account navigation must leave room for focused content and sticky panels.
    const updateHeight = () => {
      document.documentElement.style.setProperty('--portal-header-height', `${element.offsetHeight}px`);
      updateVisibility();
    };
    const onScroll = () => {
      if (frame === null) frame = window.requestAnimationFrame(() => { frame = null; updateVisibility(); });
    };
    updateHeight();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updateHeight);
    observer?.observe(element);
    if (main.current) observer?.observe(main.current);
    window.addEventListener('resize', updateHeight);
    if (results) window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', updateHeight);
      window.removeEventListener('scroll', onScroll);
      if (frame !== null) window.cancelAnimationFrame(frame);
      element.removeAttribute('data-catalogue-hidden');
      document.documentElement.style.removeProperty('--portal-header-height');
    };
  }, [location.pathname]);
  useEffect(() => {
    const titles: Record<string, string> = { '/catalogo': 'Catálogo', '/mi-lista': 'Mi lista', '/mis-reservas': 'Mis reservas', '/mis-incidencias': 'Mis avisos', '/mi-cuenta': 'Mi cuenta' };
    if (!['/acceso', '/registro'].includes(location.pathname)) document.title = `RentaLab · ${titles[location.pathname] ?? (location.pathname.startsWith('/equipos/') ? 'Equipo' : location.pathname.startsWith('/mis-reservas/') ? 'Mi reserva' : 'Página no encontrada')}`;
    if (!['/acceso', '/registro'].includes(location.pathname)) main.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [location.pathname]);
  const identity = session ? `${session.role}:${session.user?.id ?? session.username}` : 'public';
  const destination = allowedDestination(['/acceso', '/registro'].includes(location.pathname) ? new URLSearchParams(location.search).get('next') : location.pathname + location.search);
  const accessSearch = destination ? `?next=${encodeURIComponent(destination)}` : '';
  return <div className="portal-shell">
    <a className="skip-link" href="#main-content">Saltar al contenido</a>
    <header className="portal-header" ref={header}>
      <div className="portal-container portal-header-inner">
        <Link to="/catalogo" className="brand portal-brand" aria-label="RentaLab, catálogo"><BrandMark /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></Link>
        <nav aria-label="Catálogo y cuenta" className="portal-navigation">
          <NavLink to="/catalogo"><span className="portal-nav-label">Catálogo</span></NavLink>
          {session?.role !== 'admin' && <NavLink to="/mi-lista"><span className="portal-nav-label">Mi lista</span>{savedProducts.customer && !savedProducts.loading && !savedProducts.error && <span className="saved-list-count" aria-label={`${savedProducts.ids.length} equipos guardados`}>{savedProducts.ids.length}</span>}</NavLink>}
          {session?.role === 'customer' && <><NavLink to="/mis-reservas"><span className="portal-nav-label">Mis reservas</span></NavLink><NavLink to="/mis-incidencias"><span className="portal-nav-label">Mis avisos</span></NavLink><NavLink to="/mi-cuenta"><span className="portal-nav-label">Mi cuenta</span></NavLink></>}
        </nav>
        <div className="portal-header-account">
          {checking ? <span className="text-muted" role="status">Comprobando cuenta…</span>
            : checkError ? <button type="button" className="button button-secondary" onClick={() => { void checkSession(); }}>Comprobar cuenta</button>
              : session ? <>{session.role === 'admin' && <Link to="/admin" className="button button-secondary">Panel de administración</Link>}<SessionControl showIdentity={false} /></>
                : <><Link to={'/acceso' + accessSearch} className="portal-access">Acceder</Link><Link to={'/registro' + accessSearch} className="button portal-register-link">Crear cuenta</Link></>}
        </div>
      </div>
    </header>
    <main className="portal-container portal-content" id="main-content" tabIndex={-1} ref={main}>
      <div key={identity} className="portal-route"><Outlet /></div>
    </main>
    <footer className="portal-footer"><div className="portal-container portal-footer-inner"><div><strong>RentaLab</strong><p>Material audiovisual para tu próximo proyecto.</p></div><div><Link to="/catalogo">Explorar el catálogo</Link><a href="/api/public/images/photo-credits.txt" target="_blank" rel="noopener noreferrer">Créditos de fotografías</a><span>Proyecto demostrativo. Empresa y datos ficticios.</span></div></div></footer>
  </div>;
}
