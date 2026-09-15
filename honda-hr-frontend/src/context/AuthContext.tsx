import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as api from "../api";

/**
 * Who is signed in.
 *
 * The answer always comes from the server, never from anything this code
 * stores. A value kept in localStorage would say "signed in" long after the
 * session was revoked — and anyone can edit it — so the workspace would open
 * for someone the backend will refuse anyway. Here the page asks, and a 401
 * means signed out.
 */

type AuthState = {
  user: api.SignedInUser | null;
  /** Null until the first check completes, so the app can avoid flashing the
   *  login page at somebody who is already signed in. */
  ready: boolean;
  options: api.SignInOptions | null;
  refresh: () => Promise<api.SignedInUser | null>;
  setUser: (u: api.SignedInUser | null) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<api.SignedInUser | null>(null);
  const [ready, setReady] = useState(false);
  const [options, setOptions] = useState<api.SignInOptions | null>(null);

  const refresh = useCallback(async () => {
    const me = await api.whoAmI();
    setUser(me);
    setReady(true);
    return me;
  }, []);

  useEffect(() => {
    refresh();
    api.signInOptions().then(setOptions).catch(() => setOptions(null));
  }, [refresh]);

  const signOut = useCallback(async () => {
    await api.signOut();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, ready, options, refresh, setUser, signOut }),
    [user, ready, options, refresh, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
