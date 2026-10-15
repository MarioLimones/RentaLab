import { useCallback, useEffect, useRef } from 'react';

/** Una petición terminada no debe navegar ni enfocar un formulario que el usuario ya ha abandonado. */
export function useEstaMontado() {
  const montado = useRef(false);
  useEffect(() => {
    montado.current = true;
    return () => { montado.current = false; };
  }, []);
  return useCallback(() => montado.current, []);
}
