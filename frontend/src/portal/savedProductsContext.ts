import { createContext, useContext } from 'react';

export interface SavedProductsState {
  customer: boolean;
  admin: boolean;
  checking: boolean;
  ids: number[];
  loading: boolean;
  pending: boolean;
  error: string | null;
  reload: () => void;
  change: (id: number, saved: boolean) => Promise<void>;
}

export const SavedProductsContext = createContext<SavedProductsState>({
  customer: false, admin: false, checking: false, ids: [], loading: false, pending: false, error: null,
  reload: () => {}, change: async () => {},
});

export function useSavedProducts() {
  return useContext(SavedProductsContext);
}
