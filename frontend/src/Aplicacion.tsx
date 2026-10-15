import { useEffect, useRef, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { ProveedorAutenticacion } from './autenticacion/ProveedorAutenticacion';
import { useAutenticacion } from './autenticacion/contexto';
import { urlAcceso } from './autenticacion/destinos';
import type { RolUsuario } from './tipos/api';
import AplicacionAdministracion from './administracion/AplicacionAdministracion';
import { Aviso } from './componentes/interfaz';
import PaginaAcceso from './paginas/PaginaAcceso';
import EstructuraCliente from './portal/DisposicionCliente';
import { PaginaCatalogo } from './portal/PaginaCatalogo';
import { PaginaProducto } from './portal/PaginaProducto';
import PaginaMisReservas from './portal/PaginaMisReservas';
import PaginaMiReserva from './portal/PaginaMiReserva';
import PaginaMisIncidencias from './portal/PaginaMisIncidencias';
import PaginaMiCuenta from './portal/PaginaMiCuenta';
import PaginaProductosGuardados from './portal/PaginaProductosGuardados';

function ExigirRol({ rol, children }: { rol: RolUsuario; children?: ReactNode }) {
  const { sesion, comprobando, errorComprobacion, comprobarSesion } = useAutenticacion();
  const ubicacion = useLocation();
  const encabezadoDenegado = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!comprobando && sesion && sesion.role !== rol) {
      document.title = 'RentaLab · Acceso restringido';
      encabezadoDenegado.current?.focus();
    }
  }, [comprobando, sesion, rol]);
  if (comprobando) return <section className="auth-layout"><p role="status">Comprobando la sesión…</p></section>;
  if (errorComprobacion) return <section className="auth-layout"><div className="auth-card"><h1>Comprobar el acceso</h1><Aviso tono="error">{errorComprobacion}</Aviso><button className="button" onClick={() => { void comprobarSesion(); }}>Volver a comprobar</button></div></section>;
  if (!sesion) return <Navigate to={urlAcceso(ubicacion.pathname + ubicacion.search)} replace />;
  if (sesion.role !== rol) return <section className="auth-layout"><div className="auth-card"><h1 ref={encabezadoDenegado} tabIndex={-1}>Acceso restringido</h1><Aviso tono="error">Tu cuenta no tiene permisos para acceder a esta zona.</Aviso><Link className="button" to={sesion.role === 'admin' ? '/admin' : '/mi-cuenta'}>Volver a mi zona</Link></div></section>;
  return children ?? <Outlet />;
}

function RutaAdministracionAnterior() {
  const ubicacion = useLocation();
  return <Navigate to={'/admin' + ubicacion.pathname + ubicacion.search} replace />;
}

export default function Aplicacion() {
  return <ProveedorAutenticacion><Routes>
    <Route path="/admin/*" element={<ExigirRol rol="admin"><AplicacionAdministracion /></ExigirRol>} />
    <Route element={<EstructuraCliente />}>
      <Route index element={<Navigate to="/catalogo" replace />} />
      <Route path="/catalogo" element={<PaginaCatalogo />} />
      <Route path="/equipos/:id" element={<PaginaProducto />} />
      <Route path="/acceso" element={<PaginaAcceso key="login" />} />
      <Route path="/registro" element={<PaginaAcceso key="register" />} />
      <Route element={<ExigirRol rol="customer" />}>
        <Route path="/mi-lista" element={<PaginaProductosGuardados />} />
        <Route path="/mis-reservas" element={<PaginaMisReservas />} />
        <Route path="/mis-reservas/:id" element={<PaginaMiReserva />} />
        <Route path="/mis-incidencias" element={<PaginaMisIncidencias />} />
        <Route path="/mi-cuenta" element={<PaginaMiCuenta />} />
      </Route>
      <Route>
        <Route path="/equipos" element={<RutaAdministracionAnterior />} />
        <Route path="/equipos/nuevo" element={<RutaAdministracionAnterior />} />
        <Route path="/equipos/:id/editar" element={<RutaAdministracionAnterior />} />
        <Route path="/reservas/*" element={<RutaAdministracionAnterior />} />
        <Route path="/incidencias/*" element={<RutaAdministracionAnterior />} />
        <Route path="/importaciones" element={<RutaAdministracionAnterior />} />
      </Route>
      <Route path="*" element={<section><h1>Página no encontrada</h1><p>La dirección no corresponde a una pantalla de RentaLab.</p><Link className="button" to="/catalogo">Volver al catálogo</Link></section>} />
    </Route>
  </Routes></ProveedorAutenticacion>;
}
