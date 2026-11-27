import { createContext } from 'react';

import { AuthMode, User } from '../types';

export interface AuthState {
  mode: AuthMode | null;
  mcpEnabled: boolean;
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

// Kept apart from AuthContext.tsx so that file only exports components and
// hooks; useCan reads it without requiring a provider.
export const AuthContext = createContext<AuthState | undefined>(undefined);
