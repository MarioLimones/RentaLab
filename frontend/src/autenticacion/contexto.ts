import { createContext, useContext } from 'react';
import type { SesionAutenticacion, EntradaAcceso } from '../tipos/api';

export interface EstadoAutenticacion {
  sesion: SesionAutenticacion | null;
  comprobando: boolean;
  errorComprobacion: string | null;
  caducado: boolean;
  comprobarSesion: () => Promise<void>;
  iniciarSesion: (entrada: EntradaAcceso) => Promise<void>;
  cerrarSesionUsuario: () => Promise<void>;
}

export const ContextoAutenticacion = createContext<EstadoAutenticacion | null>(null);

export function useAutenticacion(): EstadoAutenticacion {
  const contexto = useContext(ContextoAutenticacion);
  if (!contexto) throw new Error('El acceso requiere AuthProvider.');
  return contexto;
}
