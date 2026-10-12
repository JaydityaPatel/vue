import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { fetchCurrentUser, loginUser, registerUser } from '../api/auth';
import { TOKEN_KEY } from '../api/client';
import type { RegisterInput, User } from '../types';

interface AuthValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) { setLoading(false); return () => { mounted = false; }; }
    fetchCurrentUser()
      .then(current => { if (mounted) setUser(current); })
      .catch(() => { localStorage.removeItem(TOKEN_KEY); if (mounted) setUser(null); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  const value = useMemo<AuthValue>(() => ({
    user,
    loading,
    async login(email, password) {
      const result = await loginUser(email, password);
      localStorage.setItem(TOKEN_KEY, result.access_token);
      const current = await fetchCurrentUser();
      setUser(current);
    },
    async register(input) {
      await registerUser(input);
      const result = await loginUser(input.email, input.password);
      localStorage.setItem(TOKEN_KEY, result.access_token);
      setUser(await fetchCurrentUser());
    },
    logout() {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    },
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
