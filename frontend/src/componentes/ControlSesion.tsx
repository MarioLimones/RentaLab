import { useState } from 'react';
import { useAutenticacion } from '../autenticacion/contexto';
import { Aviso } from './interfaz';

export default function ControlSesion({ mostrarIdentidad = true }: { mostrarIdentidad?: boolean }) {
  const { sesion, cerrarSesionUsuario } = useAutenticacion();
  const [pendiente, establecerPendiente] = useState(false);
  const [error, establecerError] = useState<string | null>(null);
  async function cerrarSesion() {
    if (pendiente) return;
    establecerPendiente(true);
    establecerError(null);
    try { await cerrarSesionUsuario(); }
    catch (fallo) { establecerError(fallo instanceof Error ? fallo.message : 'No se pudo cerrar la sesión. Inténtalo de nuevo.'); }
    finally { establecerPendiente(false); }
  }
  return <div className="session-control">
    {mostrarIdentidad && <span className="operator-name">{sesion?.user?.name ?? sesion?.username}</span>}
    <button type="button" className="button button-secondary" disabled={pendiente} onClick={() => { void cerrarSesion(); }}>{pendiente ? 'Cerrando sesión…' : 'Cerrar sesión'}</button>
    {error && <Aviso tono="error">{error}</Aviso>}
  </div>;
}
