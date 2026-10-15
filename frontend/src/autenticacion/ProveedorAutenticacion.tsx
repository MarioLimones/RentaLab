import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ErrorApi, suscribirSinAutorizacion } from '../api/cliente';
import type { SesionAutenticacion } from '../tipos/api';
import { ContextoAutenticacion } from './contexto';

export function ProveedorAutenticacion({ children }: { children: ReactNode }) {
  const [sesion, establecerSesion] = useState<SesionAutenticacion | null>(null);
  const [comprobando, establecerComprobando] = useState(true);
  const [errorComprobacion, establecerErrorComprobacion] = useState<string | null>(null);
  const [caducado, establecerCaducado] = useState(false);
  const version = useRef(0);
  const comprobarSesion = useCallback(async () => {
    const actual = ++version.current;
    establecerComprobando(true);
    establecerErrorComprobacion(null);
    try {
      const resultado = await api.sesion();
      if (version.current === actual) establecerSesion(resultado);
    } catch (error) {
      if (version.current !== actual) return;
      establecerSesion(null);
      if (!(error instanceof ErrorApi && error.estado === 401)) {
        establecerErrorComprobacion(error instanceof Error ? error.message : 'No se pudo comprobar la sesión.');
      }
    } finally { if (version.current === actual) establecerComprobando(false); }
  }, []);

  useEffect(() => {
    let actual = true;
    const cancelarSuscripcion = suscribirSinAutorizacion(() => {
      version.current += 1;
      establecerSesion(null);
      establecerComprobando(false);
      establecerErrorComprobacion(null);
      establecerCaducado(true);
    });
    void Promise.resolve().then(() => { if (actual) return comprobarSesion(); });
    return () => { actual = false; version.current += 1; cancelarSuscripcion(); };
  }, [comprobarSesion]);

  return <ContextoAutenticacion.Provider value={{
    sesion, comprobando, errorComprobacion, caducado, comprobarSesion,
    iniciarSesion: async (entrada) => {
      const resultado = await api.iniciarSesion(entrada);
      version.current += 1;
      establecerSesion(resultado);
      establecerCaducado(false);
    },
    cerrarSesionUsuario: async () => {
      await api.cerrarSesionUsuario();
      version.current += 1;
      establecerSesion(null);
      establecerCaducado(false);
    },
  }}>{children}</ContextoAutenticacion.Provider>;
}
