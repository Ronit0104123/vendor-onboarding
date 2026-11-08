import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setCsrfToken, setUnauthorizedHandler } from "./api";
import type { Me } from "./types";

interface AuthState {
  me: Me | null;
  checking: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: (everywhere?: boolean) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);

  const accept = (m: Me | null) => {
    setMe(m);
    setCsrfToken(m?.csrf_token ?? "");
  };

  useEffect(() => {
    setUnauthorizedHandler(() => accept(null));
    if (window.location.pathname.startsWith("/portal/")) { setChecking(false); return; } // vendors have no session
    api.get<{ user: Me | null }>("/api/auth/session", { auth: false }).then((r) => accept(r.user)).catch(() => accept(null)).finally(() => setChecking(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    accept(await api.post<Me>("/api/auth/login", { email, password }, { auth: false }));
  }, []);

  const logout = useCallback(async (everywhere = false) => {
    try { await api.post(everywhere ? "/api/auth/logout-all" : "/api/auth/logout"); } finally { accept(null); }
  }, []);

  return <AuthContext.Provider value={{ me, checking, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
