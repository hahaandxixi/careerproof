"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, errorMessage, type CurrentUser, type UserRole } from "@/lib/api/client";

type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

interface AuthContextValue {
  user: CurrentUser | null;
  status: AuthStatus;
  error: string;
  login(email: string, password: string): Promise<CurrentUser>;
  register(payload: {
    email: string;
    password: string;
    displayName: string;
    role: Exclude<UserRole, "admin">;
  }): Promise<CurrentUser>;
  logout(): Promise<void>;
  reload(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState("");
  const operation = useRef(0);

  const reload = useCallback(async () => {
    const currentOperation = ++operation.current;
    setError("");
    try {
      const current = await api.getMe();
      if (currentOperation !== operation.current) return;
      setUser(current);
      setStatus("authenticated");
    } catch (reason) {
      if (currentOperation !== operation.current) return;
      if (reason instanceof ApiError && reason.status === 401) {
        setUser(null);
        setStatus("unauthenticated");
      } else {
        setError(errorMessage(reason));
        setStatus("error");
      }
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    const expired = () => { setUser(null); setStatus("unauthenticated"); setError(""); };
    window.addEventListener("careerproof:session-expired", expired);
    return () => window.removeEventListener("careerproof:session-expired", expired);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      error,
      async login(email, password) {
        ++operation.current;
        const data = await api.login({ email, password });
        setUser(data.user);
        setError("");
        setStatus("authenticated");
        return data.user;
      },
      async register(payload) {
        ++operation.current;
        const data = await api.register(payload);
        setUser(data.user);
        setError("");
        setStatus("authenticated");
        return data.user;
      },
      async logout() {
        ++operation.current;
        await api.logout();
        setUser(null);
        setError("");
        setStatus("unauthenticated");
      },
      reload,
    }),
    [error, reload, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
