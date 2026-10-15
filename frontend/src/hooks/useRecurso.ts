import { useEffect, useReducer, useState } from 'react';

export function useRecurso<T>(cargador: () => Promise<T>) {
  const [version, actualizar] = useReducer((valor: number) => valor + 1, 0);
  const [estadoInterno, establecerEstadoInterno] = useState<{ datos: T | null; cargando: boolean; error: string | null }>({ datos: null, cargando: true, error: null });
  useEffect(() => {
    let actual = true;
    // Una microtarea también permite tratar de forma uniforme los fallos síncronos de la carga.
    void Promise.resolve().then(() => {
      if (actual) establecerEstadoInterno((anterior) => ({ ...anterior, cargando: true, error: null }));
      return cargador();
    }).then(
      (datos) => { if (actual) establecerEstadoInterno({ datos, cargando: false, error: null }); },
      (error: unknown) => { if (actual) establecerEstadoInterno((anterior) => ({ ...anterior, cargando: false, error: error instanceof Error ? error.message : 'No se pudieron cargar los datos.' })); },
    );
    return () => { actual = false; };
  }, [cargador, version]);
  return { ...estadoInterno, recargar: actualizar };
}
