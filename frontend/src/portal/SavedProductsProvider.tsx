import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import { SavedProductsContext } from './savedProductsContext';

/** One provider per account; requests from a previous account never populate a new list. */
export function SavedProductsProvider({ customer, admin = false, checking = false, children }: { customer: boolean; admin?: boolean; checking?: boolean; children: ReactNode }) {
  const [state, setState] = useState({ ids: [] as number[], loading: customer, error: null as string | null });
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(false);
  const changing = useRef(false);
  const alive = useRef(false);
  const loadVersion = useRef(0);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!customer) return;
    const controller = new AbortController();
    const version = ++loadVersion.current;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setState((previous) => ({ ...previous, loading: true, error: null }));
      const result = await api.listSavedProducts(controller.signal);
      if (active && version === loadVersion.current) setState({ ids: result.equipment_ids, loading: false, error: null });
    }).catch((error: unknown) => {
      if (active && version === loadVersion.current) setState((previous) => ({ ...previous, loading: false, error: error instanceof Error ? error.message : 'No se pudo cargar tu lista.' }));
    });
    return () => { active = false; controller.abort(); };
  }, [customer, revision]);

  async function change(id: number, saved: boolean) {
    if (!customer || changing.current) return;
    changing.current = true;
    setPending(true);
    ++loadVersion.current;
    try {
      const result = await (saved ? api.saveProduct(id) : api.removeSavedProduct(id));
      if (alive.current) setState({ ids: result.equipment_ids, loading: false, error: null });
    } finally {
      changing.current = false;
      if (alive.current) setPending(false);
    }
  }

  return <SavedProductsContext.Provider value={{ customer, admin, checking, ...state, pending, reload: () => { if (!changing.current) setRevision((value) => value + 1); }, change }}>{children}</SavedProductsContext.Provider>;
}
