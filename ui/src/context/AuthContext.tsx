import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi, auth } from '../services/api';
import { AuthMode, User } from '../types';

interface AuthState {
  mode: AuthMode | null;
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const config = await authApi.getConfig();
      setMode(config.mode);
      try {
        setUser(await authApi.me());
      } catch {
        setUser(null);
      }
    } catch (error) {
      console.error('Failed to load auth config:', error);
      setMode(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener('voicevault:unauthorized', onUnauthorized);
    return () => window.removeEventListener('voicevault:unauthorized', onUnauthorized);
  }, []);

  const loginWithToken = useCallback(
    async (token: string) => {
      await authApi.login(token);
      auth.setToken(token);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // session may already be gone — still clear local state
    }
    auth.removeToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        mode,
        user,
        isLoading,
        isAuthenticated: user !== null,
        loginWithToken,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthState => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
