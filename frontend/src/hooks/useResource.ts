import { useEffect, useReducer, useState } from 'react';

export function useResource<T>(loader: () => Promise<T>) {
  const [version, refresh] = useReducer((value: number) => value + 1, 0);
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: string | null }>({ data: null, loading: true, error: null });
  useEffect(() => {
    let current = true;
    // A microtask also handles synchronous failures from a loader consistently.
    void Promise.resolve().then(() => {
      if (current) setState((previous) => ({ ...previous, loading: true, error: null }));
      return loader();
    }).then(
      (data) => { if (current) setState({ data, loading: false, error: null }); },
      (error: unknown) => { if (current) setState((previous) => ({ ...previous, loading: false, error: error instanceof Error ? error.message : 'No se pudieron cargar los datos.' })); },
    );
    return () => { current = false; };
  }, [loader, version]);
  return { ...state, reload: refresh };
}
