import { createContext, useContext } from 'react';

export interface EstadoProductosGuardados {
  cliente: boolean;
  administracion: boolean;
  comprobando: boolean;
  ids: number[];
  cargando: boolean;
  pendiente: boolean;
  error: string | null;
  recargar: () => void;
  cambio: (id: number, guardado: boolean) => Promise<void>;
}

export const ContextoProductosGuardados = createContext<EstadoProductosGuardados>({
  cliente: false, administracion: false, comprobando: false, ids: [], cargando: false, pendiente: false, error: null,
  recargar: () => {}, cambio: async () => {},
});

export function useProductosGuardados() {
  return useContext(ContextoProductosGuardados);
}
