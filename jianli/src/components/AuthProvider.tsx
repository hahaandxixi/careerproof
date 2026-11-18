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
        // A failed background read cannot confirm that the signed-in user changed.
        setStatus(previous => previous === "authenticated" ? previous : "error");
      }
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    // Another tab may have logged in, logged out, or switched accounts while
    // this tab was hidden. Re-read the current cookie-backed identity on return.
    const synchronize = () => {
      if (document.visibilityState !== "hidden") void reload();
    };
    window.addEventListener("focus", synchronize);
    window.addEventListener("pageshow", synchronize);
    document.addEventListener("visibilitychange", synchronize);
    return () => {
      window.removeEventListener("focus", synchronize);
      window.removeEventListener("pageshow", synchronize);
      document.removeEventListener("visibilitychange", synchronize);
    };
  }, [reload]);

  useEffect(() => {
    // A stale request can arrive after another tab has renewed shared cookies.
    // Confirm the current session before replacing the visible account state.
    const expired = () => { void reload(); };
    window.addEventListener("careerproof:session-expired", expired);
    return () => window.removeEventListener("careerproof:session-expired", expired);
  }, [reload]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      error,
      async login(email, password) {
        ++operation.current;
        const data = await api.login({ email, password });
        ++operation.current;
        setUser(data.user);
        setError("");
        setStatus("authenticated");
        return data.user;
      },
      async register(payload) {
        ++operation.current;
        const data = await api.register(payload);
        ++operation.current;
        setUser(data.user);
        setError("");
        setStatus("authenticated");
        return data.user;
      },
      async logout() {
        ++operation.current;
        await api.logout();
        ++operation.current;
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
