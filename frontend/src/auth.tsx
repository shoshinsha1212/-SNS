import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearToken, errorMessage, getDeviceId, getToken, setToken, type User } from "./api";

type AuthState = {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (user: User, token: string) => void;
  logout: () => void;
  reload: () => void;
  updateProfile: (handle: string, attributes: Record<string, string>) => Promise<User>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    const token = getToken();
    setLoading(true);
    setError(null);

    if (token) {
      api
        .getMe()
        .then(setUser)
        .catch((e) => {
          if (e instanceof ApiError && e.status === 401) {
            clearToken();
            // トークンが無効な場合、端末IDで既存ユーザーに自動再接続
            api
              .createUser("ゲスト参加者", {}, getDeviceId())
              .then((res) => {
                setToken(res.token);
                setUser(res.user);
              })
              .catch(() => setUser(null));
          } else {
            setError(errorMessage(e));
          }
        })
        .finally(() => setLoading(false));
    } else {
      // トークンがない初回アクセス時、端末ID（device_id）で1つの固定ユーザーを自動割り当て・復元
      api
        .createUser("ゲスト参加者", {}, getDeviceId())
        .then((res) => {
          setToken(res.token);
          setUser(res.user);
        })
        .catch((e) => {
          setError(errorMessage(e));
        })
        .finally(() => setLoading(false));
    }
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

  const updateProfile = useCallback(async (handle: string, attributes: Record<string, string>) => {
    const updated = await api.updateMe(handle, attributes);
    setUser(updated);
    return updated;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout, reload, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider がありません");
  return ctx;
}
