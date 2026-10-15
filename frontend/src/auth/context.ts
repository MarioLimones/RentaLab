import { createContext, useContext } from 'react';
import type { AuthSession, LoginInput } from '../types/api';

export interface AuthState {
  session: AuthSession | null;
  checking: boolean;
  checkError: string | null;
  expired: boolean;
  checkSession: () => Promise<void>;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error('El acceso requiere AuthProvider.');
  return context;
}
