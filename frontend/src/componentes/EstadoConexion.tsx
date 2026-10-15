import { useEffect, useState } from 'react';
import { api } from '../api/cliente';

type EstadoConexion = { clase: 'checking' } | { clase: 'connected' } | { clase: 'error'; mensaje: string };

export default function SituacionConexion() {
  const [estadoInterno, establecerEstadoInterno] = useState<EstadoConexion>({ clase: 'checking' });
  const [intento, establecerIntento] = useState(0);
  useEffect(() => {
    const controlador = new AbortController();
    void api.saludServicio(controlador.signal).then(
      () => { if (!controlador.signal.aborted) establecerEstadoInterno({ clase: 'connected' }); },
      (error: unknown) => { if (!controlador.signal.aborted) establecerEstadoInterno({ clase: 'error', mensaje: error instanceof Error ? error.message : 'No se pudo comprobar la conexión.' }); },
    );
    return () => controlador.abort();
  }, [intento]);
  function comprobarOtraVez() { establecerEstadoInterno({ clase: 'checking' }); establecerIntento((anterior) => anterior + 1); }
  return <section className="connection-status" aria-labelledby="connection-heading">
    <h2 id="connection-heading">Estado del servidor</h2>
    <div className="connection-state" data-state={estadoInterno.clase} role={estadoInterno.clase === 'error' ? 'alert' : 'status'}>
      <span className="status-dot" aria-hidden="true" />
      <span>{estadoInterno.clase === 'connected' ? 'Conexión establecida' : estadoInterno.clase === 'checking' ? 'Comprobando conexión' : estadoInterno.mensaje}</span>
    </div>
    <button type="button" className="connection-retry" disabled={estadoInterno.clase === 'checking'} onClick={comprobarOtraVez}>{estadoInterno.clase === 'checking' ? 'Comprobando…' : 'Volver a comprobar'}</button>
    <a href="/api/docs">Documentación de la API</a>
  </section>;
}
