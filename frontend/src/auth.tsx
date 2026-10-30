import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearToken, errorMessage, getToken, setToken, type User } from "./api";

type AuthState = {
  user: User | null;
  loading: boolean;
  error: string | null; // 401 以外の取得エラー（サーバー未起動など）
  login: (user: User, token: string) => void;
  logout: () => void;
  reload: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .getMe()
      .then(setUser)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          clearToken();
          setUser(null);
        } else {
          setError(errorMessage(e));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const login = useCallback((u: User, token: string) => {
    setToken(token);
    setUser(u);
    setError(null);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout, reload }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider がありません");
  return ctx;
}
