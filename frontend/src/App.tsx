import { useEffect, useRef, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { useAuth } from './auth/context';
import { accessUrl } from './auth/destinations';
import type { UserRole } from './types/api';
import AdminApp from './admin/AdminApp';
import { Notice } from './components/ui';
import LoginPage from './pages/LoginPage';
import ClientLayout from './portal/ClientLayout';
import { CataloguePage } from './portal/CataloguePage';
import { ProductPage } from './portal/ProductPage';
import MyReservationsPage from './portal/MyReservationsPage';
import MyReservationPage from './portal/MyReservationPage';
import MyIncidentsPage from './portal/MyIncidentsPage';
import MyAccountPage from './portal/MyAccountPage';
import SavedProductsPage from './portal/SavedProductsPage';

function RequireRole({ role, children }: { role: UserRole; children?: ReactNode }) {
  const { session, checking, checkError, checkSession } = useAuth();
  const location = useLocation();
  const deniedHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!checking && session && session.role !== role) {
      document.title = 'RentaLab · Acceso restringido';
      deniedHeading.current?.focus();
    }
  }, [checking, session, role]);
  if (checking) return <section className="auth-layout"><p role="status">Comprobando la sesión…</p></section>;
  if (checkError) return <section className="auth-layout"><div className="auth-card"><h1>Comprobar el acceso</h1><Notice tone="error">{checkError}</Notice><button className="button" onClick={() => { void checkSession(); }}>Volver a comprobar</button></div></section>;
  if (!session) return <Navigate to={accessUrl(location.pathname + location.search)} replace />;
  if (session.role !== role) return <section className="auth-layout"><div className="auth-card"><h1 ref={deniedHeading} tabIndex={-1}>Acceso restringido</h1><Notice tone="error">Tu cuenta no tiene permisos para acceder a esta zona.</Notice><Link className="button" to={session.role === 'admin' ? '/admin' : '/mi-cuenta'}>Volver a mi zona</Link></div></section>;
  return children ?? <Outlet />;
}

function LegacyAdminRoute() {
  const location = useLocation();
  return <Navigate to={'/admin' + location.pathname + location.search} replace />;
}

export default function App() {
  return <AuthProvider><Routes>
    <Route path="/admin/*" element={<RequireRole role="admin"><AdminApp /></RequireRole>} />
    <Route element={<ClientLayout />}>
      <Route index element={<Navigate to="/catalogo" replace />} />
      <Route path="/catalogo" element={<CataloguePage />} />
      <Route path="/equipos/:id" element={<ProductPage />} />
      <Route path="/acceso" element={<LoginPage key="login" />} />
      <Route path="/registro" element={<LoginPage key="register" />} />
      <Route element={<RequireRole role="customer" />}>
        <Route path="/mi-lista" element={<SavedProductsPage />} />
        <Route path="/mis-reservas" element={<MyReservationsPage />} />
        <Route path="/mis-reservas/:id" element={<MyReservationPage />} />
        <Route path="/mis-incidencias" element={<MyIncidentsPage />} />
        <Route path="/mi-cuenta" element={<MyAccountPage />} />
      </Route>
      <Route>
        <Route path="/equipos" element={<LegacyAdminRoute />} />
        <Route path="/equipos/nuevo" element={<LegacyAdminRoute />} />
        <Route path="/equipos/:id/editar" element={<LegacyAdminRoute />} />
        <Route path="/reservas/*" element={<LegacyAdminRoute />} />
        <Route path="/incidencias/*" element={<LegacyAdminRoute />} />
        <Route path="/importaciones" element={<LegacyAdminRoute />} />
      </Route>
      <Route path="*" element={<section><h1>Página no encontrada</h1><p>La dirección no corresponde a una pantalla de RentaLab.</p><Link className="button" to="/catalogo">Volver al catálogo</Link></section>} />
    </Route>
  </Routes></AuthProvider>;
}
