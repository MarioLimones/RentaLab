import { useCallback, useEffect, useRef } from 'react';

/** A finished request must not navigate or focus a form the user has left. */
export function useIsMounted() {
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return useCallback(() => mounted.current, []);
}
