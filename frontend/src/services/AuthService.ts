/**
 * Auth service — the single seam between the UI and the identity provider.
 *
 * Supabase Auth is the single source of truth: the Supabase client owns all
 * session storage (persistSession) and refresh logic. This service only maps
 * sessions into the app's shape and hands them to AuthContext — no
 * localStorage here.
 */
import { supabase } from "@/lib/supabase";
import * as authApi from "@/api/auth.api";
import { setAccessToken } from "@/api/http";
import { STORAGE_KEYS } from "@/constants";
import type { AuthUser, Session } from "@/types/api/auth.contracts";

/** Last known session, kept in memory so restoreSession() stays synchronous. */
let cachedSession: Session | null = null;

// Supabase's getSession() is async. Kick the persisted-session read off once,
// here at module load, so rehydration overlaps the first render instead of
// happening after it. AuthContext awaits `hydrateSession()` (which awaits this
// bootstrap) before flipping `ready`, so the session and token settle before
// any authenticated request fires.
const bootPromise = (async (): Promise<Session | null> => {
  try {
    const { data, error } = await supabase.auth.getSession();
    if (error || !data.session) return null;
    const session = await authApi.mapSession(data.session);
    if (!session) return null;
    cachedSession = session;
    setAccessToken(session.access_token);
    return session;
  } catch {
    /* Supabase not configured yet — app starts signed out. */
    return null;
  }
})();

// Keep the HTTP client's token in sync when Supabase refreshes the session in
// the background (autoRefreshToken) or the user signs in/out elsewhere. Without
// this, a token renewal would leave the module holding a now-expired access
// token, producing sporadic 401s on a cold file.
supabase.auth.onAuthStateChange((event, session) => {
  if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED" || event === "SIGNED_OUT") {
    setAccessToken(session?.access_token ?? null);
  }
});

export const AuthService = {
  /**
   * Resolve the persisted Supabase session at boot and load its access token
   * into the HTTP client. Awaiting this guarantees the token is set before the
   * workspace bootstrap (or any authenticated call) runs.
   */
  async hydrateSession(): Promise<Session | null> {
    const session = await bootPromise;
    cachedSession = session;
    setAccessToken(session?.access_token ?? null);
    return session;
  },

  /**
   * Restore the persisted Supabase session at boot.
   * Synchronous by design: the value is hydrated from `supabase.auth.getSession()`.
   */
  restoreSession(): Session | null {
    setAccessToken(cachedSession?.access_token ?? null);
    return cachedSession;
  },

  /** Sign in with email + password and cache the resulting session. */
  async login(email: string, password: string, remember = true): Promise<Session> {
    // Flip the remember flag BEFORE the sign-in call so the storage adapter
    // writes the fresh token to localStorage (remembered) or memory (not).
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEYS.remember, remember ? "1" : "0");
    }
    const { session } = await authApi.login({ email, password });
    cachedSession = session;
    setAccessToken(session.access_token);
    return session;
  },

  /** Sign the user out, clearing the cached session. */
  async logout(): Promise<void> {
    await authApi.logout();
    cachedSession = null;
    setAccessToken(null);
  },

  /** Resolve the current user, merging profiles + user_roles into AuthUser. */
  async getCurrentUser(): Promise<AuthUser | null> {
    const { user } = await authApi.getCurrentUser(cachedSession);
    return user;
  },

  /** Refresh the active session, falling back to the persisted session if needed. */
  async refreshSession(): Promise<Session | null> {
    if (cachedSession) {
      const { session } = await authApi.refreshSession(cachedSession);
      cachedSession = session;
      setAccessToken(session.access_token);
      return session;
    }

    const { data } = await supabase.auth.getSession();
    if (!data.session) return null;
    const session = await authApi.mapSession(data.session);
    if (!session) return null;
    cachedSession = session;
    setAccessToken(session.access_token);
    return session;
  },

  listDemoAccounts: authApi.listDemoAccounts,
  demoAccounts: authApi.demoAccounts,
};
