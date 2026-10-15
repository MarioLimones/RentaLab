import { useEffect, useRef } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import ConnectionStatus from '../components/ConnectionStatus';
import Icon from '../components/Icon';
import BrandMark from '../components/BrandMark';
import { PageHeader } from '../components/ui';
import { DashboardPage } from '../pages/DashboardPage';
import { EquipmentPage } from '../pages/EquipmentPage';
import { EquipmentFormPage } from '../pages/EquipmentFormPage';
import { EquipmentDetailPage } from '../pages/EquipmentDetailPage';
import ReservationsPage from '../pages/ReservationsPage';
import ReservationFormPage from '../pages/ReservationFormPage';
import ReservationDetailPage from '../pages/ReservationDetailPage';
import IncidentsPage from '../pages/IncidentsPage';
import IncidentFormPage from '../pages/IncidentFormPage';
import IncidentDetailPage from '../pages/IncidentDetailPage';
import ImportsPage from '../pages/ImportsPage';
import SessionControl from '../components/SessionControl';


const navigation = [
  { to: '/admin', label: 'Resumen', icon: 'overview' },
  { to: '/admin/equipos', label: 'Equipos', icon: 'equipment' },
  { to: '/admin/reservas', label: 'Reservas', icon: 'reservations' },
  { to: '/admin/incidencias', label: 'Incidencias', icon: 'incidents' },
  { to: '/admin/importaciones', label: 'Importaciones', icon: 'imports' },
] as const;

export default function AdminApp() {
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const active = navigation.find((item) => item.to !== '/admin' && location.pathname.startsWith(item.to));
    document.title = `RentaLab · ${active?.label ?? 'Resumen'}`;
    main.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [location.pathname]);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Saltar al contenido</a>
    <aside className="sidebar">
      <Link to="/admin" className="brand" aria-label="RentaLab, resumen"><BrandMark /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></Link>
      <p className="nav-label">Espacio de trabajo</p>
      <nav aria-label="Principal"><ul>{navigation.map((item) => <li key={item.to}><NavLink to={item.to} end={item.to === '/admin'}><Icon name={item.icon} /><span>{item.label}</span></NavLink></li>)}</ul></nav>
      <div className="sidebar-footer"><ConnectionStatus /><div className="demo-note"><strong>Proyecto demostrativo</strong><span>Empresa y datos ficticios</span></div></div>
    </aside>
    <div className="workspace">
      <header className="workspace-bar"><Link to="/catalogo">Ver catálogo público</Link><div className="workspace-session"><span className="environment-label"><span aria-hidden="true" />Demostración local</span><SessionControl /></div></header>
      <main id="main-content" tabIndex={-1} ref={main}>
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="equipos" element={<EquipmentPage />} />
          <Route path="equipos/nuevo" element={<EquipmentFormPage />} />
          <Route path="equipos/:id" element={<EquipmentDetailPage />} />
          <Route path="equipos/:id/editar" element={<EquipmentFormPage />} />
          <Route path="reservas" element={<ReservationsPage />} />
          <Route path="reservas/nueva" element={<ReservationFormPage />} />
          <Route path="reservas/:id" element={<ReservationDetailPage />} />
          <Route path="incidencias" element={<IncidentsPage />} />
          <Route path="incidencias/nueva" element={<IncidentFormPage />} />
          <Route path="incidencias/:id" element={<IncidentDetailPage />} />
          <Route path="importaciones" element={<ImportsPage />} />
          <Route path="*" element={<><PageHeader title="Página no encontrada" description="La dirección no corresponde a una pantalla de RentaLab." /><Link className="button" to="/admin">Volver al resumen</Link></>} />
        </Routes>
      </main>
      <footer className="workspace-footer">RentaLab <span>Una unidad, una reserva. Todo su historial.</span></footer>
    </div>
  </div>;
}
