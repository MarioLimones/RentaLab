import { useState } from 'react';
import { useAuth } from '../auth/context';
import { Notice } from './ui';

export default function SessionControl({ showIdentity = true }: { showIdentity?: boolean }) {
  const { session, logout } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function closeSession() {
    if (pending) return;
    setPending(true);
    setError(null);
    try { await logout(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo cerrar la sesión. Inténtalo de nuevo.'); }
    finally { setPending(false); }
  }
  return <div className="session-control">
    {showIdentity && <span className="operator-name">{session?.user?.name ?? session?.username}</span>}
    <button type="button" className="button button-secondary" disabled={pending} onClick={() => { void closeSession(); }}>{pending ? 'Cerrando sesión…' : 'Cerrar sesión'}</button>
    {error && <Notice tone="error">{error}</Notice>}
  </div>;
}
