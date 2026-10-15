import { useEffect, useState } from 'react';
import { api } from '../api/client';

type ConnectionState = { kind: 'checking' } | { kind: 'connected' } | { kind: 'error'; message: string };

export default function ConnectionStatus() {
  const [state, setState] = useState<ConnectionState>({ kind: 'checking' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void api.health(controller.signal).then(
      () => { if (!controller.signal.aborted) setState({ kind: 'connected' }); },
      (error: unknown) => { if (!controller.signal.aborted) setState({ kind: 'error', message: error instanceof Error ? error.message : 'No se pudo comprobar la conexión.' }); },
    );
    return () => controller.abort();
  }, [attempt]);
  function checkAgain() { setState({ kind: 'checking' }); setAttempt((previous) => previous + 1); }
  return <section className="connection-status" aria-labelledby="connection-heading">
    <h2 id="connection-heading">Estado del servidor</h2>
    <div className="connection-state" data-state={state.kind} role={state.kind === 'error' ? 'alert' : 'status'}>
      <span className="status-dot" aria-hidden="true" />
      <span>{state.kind === 'connected' ? 'Conexión establecida' : state.kind === 'checking' ? 'Comprobando conexión' : state.message}</span>
    </div>
    <button type="button" className="connection-retry" disabled={state.kind === 'checking'} onClick={checkAgain}>{state.kind === 'checking' ? 'Comprobando…' : 'Volver a comprobar'}</button>
    <a href="/api/docs">Documentación de la API</a>
  </section>;
}
