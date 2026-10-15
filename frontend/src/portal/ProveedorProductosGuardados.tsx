import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/cliente';
import { ContextoProductosGuardados } from './contextoProductosGuardados';

/** Un proveedor por cuenta; las peticiones de una cuenta anterior nunca rellenan una lista nueva. */
export function ProveedorProductosGuardados({ cliente, administracion = false, comprobando = false, children }: { cliente: boolean; administracion?: boolean; comprobando?: boolean; children: ReactNode }) {
  const [estadoInterno, establecerEstadoInterno] = useState({ ids: [] as number[], cargando: cliente, error: null as string | null });
  const [revision, establecerRevision] = useState(0);
  const [pendiente, establecerPendiente] = useState(false);
  const cambiando = useRef(false);
  const vigente = useRef(false);
  const versionCarga = useRef(0);

  useEffect(() => { vigente.current = true; return () => { vigente.current = false; }; }, []);
  useEffect(() => {
    if (!cliente) return;
    const controlador = new AbortController();
    const version = ++versionCarga.current;
    let activo = true;
    void Promise.resolve().then(async () => {
      if (!activo) return;
      establecerEstadoInterno((anterior) => ({ ...anterior, cargando: true, error: null }));
      const resultado = await api.listarProductosGuardados(controlador.signal);
      if (activo && version === versionCarga.current) establecerEstadoInterno({ ids: resultado.equipment_ids, cargando: false, error: null });
    }).catch((error: unknown) => {
      if (activo && version === versionCarga.current) establecerEstadoInterno((anterior) => ({ ...anterior, cargando: false, error: error instanceof Error ? error.message : 'No se pudo cargar tu lista.' }));
    });
    return () => { activo = false; controlador.abort(); };
  }, [cliente, revision]);

  async function cambio(id: number, guardado: boolean) {
    if (!cliente || cambiando.current) return;
    cambiando.current = true;
    establecerPendiente(true);
    ++versionCarga.current;
    try {
      const resultado = await (guardado ? api.guardarProducto(id) : api.eliminarProductoGuardado(id));
      if (vigente.current) establecerEstadoInterno({ ids: resultado.equipment_ids, cargando: false, error: null });
    } finally {
      cambiando.current = false;
      if (vigente.current) establecerPendiente(false);
    }
  }

  return <ContextoProductosGuardados.Provider value={{ cliente, administracion, comprobando, ...estadoInterno, pendiente, recargar: () => { if (!cambiando.current) establecerRevision((valor) => valor + 1); }, cambio }}>{children}</ContextoProductosGuardados.Provider>;
}
