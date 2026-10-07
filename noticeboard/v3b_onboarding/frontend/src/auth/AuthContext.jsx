import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setAuthToken, setUnauthorizedHandler } from "../api";

const STORAGE_KEY = "noticeboard.auth";

function loadSavedSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

// Restore the last session before the first render, so requests made on page load carry the token.
const savedSession = loadSavedSession();
setAuthToken(savedSession?.token ?? null);

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState(savedSession); // { token, user } or null

  /** Store a token from /auth/login or /auth/signup and make that user current. */
  const startSession = useCallback(
    (data) => {
      const next = { token: data.access_token, user: data.user };
      setAuthToken(next.token);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      // Drop every cached response from the previous identity. Query keys include the user id,
      // so the views that render for the new user fetch fresh data straight away.
      queryClient.clear();
      setSession(next);
      return next.user;
    },
    [queryClient],
  );

  const login = useCallback(
    async (identifier, password) => startSession((await api.post("/auth/login", { identifier, password })).data),
    [startSession],
  );

  /** Create a trainee account ({ name, email, password, cohort_id }) and log straight in. */
  const signup = useCallback(
    async (form) => startSession((await api.post("/auth/signup", form)).data),
    [startSession],
  );

  const logout = useCallback(() => {
    setAuthToken(null);
    localStorage.removeItem(STORAGE_KEY);
    queryClient.clear();
    setSession(null);
  }, [queryClient]);

  // If the API ever answers 401 (expired token), drop back to the login screen.
  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const value = useMemo(
    () => ({ currentToken: session?.token ?? null, currentUser: session?.user ?? null, login, signup, logout }),
    [session, login, signup, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
