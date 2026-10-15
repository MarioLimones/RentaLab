import { useEffect, useRef } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import SituacionConexion from '../componentes/EstadoConexion';
import Icono from '../componentes/Icono';
import MarcaIdentidad from '../componentes/Marca';
import { CabeceraPagina } from '../componentes/interfaz';
import { PaginaResumen } from '../paginas/PaginaResumen';
import { PaginaEquipos } from '../paginas/PaginaEquipos';
import { PaginaFormularioEquipo } from '../paginas/PaginaFormularioEquipo';
import { PaginaDetalleEquipo } from '../paginas/PaginaDetalleEquipo';
import PaginaReservas from '../paginas/PaginaReservas';
import PaginaFormularioReserva from '../paginas/PaginaFormularioReserva';
import PaginaDetalleReserva from '../paginas/PaginaDetalleReserva';
import PaginaIncidencias from '../paginas/PaginaIncidencias';
import PaginaFormularioIncidencia from '../paginas/PaginaFormularioIncidencia';
import PaginaDetalleIncidencia from '../paginas/PaginaDetalleIncidencia';
import PaginaImportaciones from '../paginas/PaginaImportaciones';
import ControlSesion from '../componentes/ControlSesion';


const navegacion = [
  { to: '/admin', label: 'Resumen', icon: 'overview' },
  { to: '/admin/equipos', label: 'Equipos', icon: 'equipment' },
  { to: '/admin/reservas', label: 'Reservas', icon: 'reservations' },
  { to: '/admin/incidencias', label: 'Incidencias', icon: 'incidents' },
  { to: '/admin/importaciones', label: 'Importaciones', icon: 'imports' },
] as const;

export default function AplicacionAdministracion() {
  const ubicacion = useLocation();
  const principal = useRef<HTMLElement>(null);
  useEffect(() => {
    const activo = navegacion.find((elementoLista) => elementoLista.to !== '/admin' && ubicacion.pathname.startsWith(elementoLista.to));
    document.title = `RentaLab · ${activo?.label ?? 'Resumen'}`;
    principal.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [ubicacion.pathname]);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Saltar al contenido</a>
    <aside className="sidebar">
      <Link to="/admin" className="brand" aria-label="RentaLab, resumen"><MarcaIdentidad /><span>RentaLab<span className="brand-subtitle">Alquiler audiovisual</span></span></Link>
      <p className="nav-label">Espacio de trabajo</p>
      <nav aria-label="Principal"><ul>{navegacion.map((elementoLista) => <li key={elementoLista.to}><NavLink to={elementoLista.to} end={elementoLista.to === '/admin'}><Icono nombre={elementoLista.icon} /><span>{elementoLista.label}</span></NavLink></li>)}</ul></nav>
      <div className="sidebar-footer"><SituacionConexion /><div className="demo-note"><strong>Proyecto demostrativo</strong><span>Empresa y datos ficticios</span></div></div>
    </aside>
    <div className="workspace">
      <header className="workspace-bar"><Link to="/catalogo">Ver catálogo público</Link><div className="workspace-session"><span className="environment-label"><span aria-hidden="true" />Demostración local</span><ControlSesion /></div></header>
      <main id="main-content" tabIndex={-1} ref={principal}>
        <Routes>
          <Route index element={<PaginaResumen />} />
          <Route path="equipos" element={<PaginaEquipos />} />
          <Route path="equipos/nuevo" element={<PaginaFormularioEquipo />} />
          <Route path="equipos/:id" element={<PaginaDetalleEquipo />} />
          <Route path="equipos/:id/editar" element={<PaginaFormularioEquipo />} />
          <Route path="reservas" element={<PaginaReservas />} />
          <Route path="reservas/nueva" element={<PaginaFormularioReserva />} />
          <Route path="reservas/:id" element={<PaginaDetalleReserva />} />
          <Route path="incidencias" element={<PaginaIncidencias />} />
          <Route path="incidencias/nueva" element={<PaginaFormularioIncidencia />} />
          <Route path="incidencias/:id" element={<PaginaDetalleIncidencia />} />
          <Route path="importaciones" element={<PaginaImportaciones />} />
          <Route path="*" element={<><CabeceraPagina titulo="Página no encontrada" descripcion="La dirección no corresponde a una pantalla de RentaLab." /><Link className="button" to="/admin">Volver al resumen</Link></>} />
        </Routes>
      </main>
      <footer className="workspace-footer">RentaLab <span>Una unidad, una reserva. Todo su historial.</span></footer>
    </div>
  </div>;
}
