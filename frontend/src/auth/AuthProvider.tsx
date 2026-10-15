import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, subscribeToUnauthorized } from '../api/client';
import type { AuthSession } from '../types/api';
import { AuthContext } from './context';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [checking, setChecking] = useState(true);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const version = useRef(0);
  const checkSession = useCallback(async () => {
    const current = ++version.current;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await api.session();
      if (version.current === current) setSession(result);
    } catch (error) {
      if (version.current !== current) return;
      setSession(null);
      if (!(error instanceof ApiError && error.status === 401)) {
        setCheckError(error instanceof Error ? error.message : 'No se pudo comprobar la sesión.');
      }
    } finally { if (version.current === current) setChecking(false); }
  }, []);

  useEffect(() => {
    let current = true;
    const unsubscribe = subscribeToUnauthorized(() => {
      version.current += 1;
      setSession(null);
      setChecking(false);
      setCheckError(null);
      setExpired(true);
    });
    void Promise.resolve().then(() => { if (current) return checkSession(); });
    return () => { current = false; version.current += 1; unsubscribe(); };
  }, [checkSession]);

  return <AuthContext.Provider value={{
    session, checking, checkError, expired, checkSession,
    login: async (input) => {
      const result = await api.login(input);
      version.current += 1;
      setSession(result);
      setExpired(false);
    },
    logout: async () => {
      await api.logout();
      version.current += 1;
      setSession(null);
      setExpired(false);
    },
  }}>{children}</AuthContext.Provider>;
}
