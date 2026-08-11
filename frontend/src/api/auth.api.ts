/**
 * Auth endpoints backed by Supabase Auth.
 *
 * These replace the old mock/FastAPI stubs. Every call flows through the
 * shared Supabase client in `src/lib/supabase.ts` — the only Supabase client
 * in the application. Supabase errors are converted to plain `Error`s here.
 */
import { supabase } from "@/lib/supabase";
import type { Session as SupabaseSession, User as SupabaseUser } from "@supabase/supabase-js";
import type {
  AuthUser,
  GetCurrentUserResponse,
  LoginRequest,
  LoginResponse,
  RefreshSessionResponse,
  Session,
} from "@/types/api/auth.contracts";
import type { DbProfile, DbUserRole } from "@/types/database.types";

/** Convert a Supabase error into a normal Error with a sane fallback message. */
function toError(error: { message?: string } | null | undefined, fallback: string): Error {
  return new Error(error?.message ?? fallback);
}

/** Best-effort initials (e.g. "Nour Atef" → "AR"). */
function initialsFor(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return initials || "?";
}

/**
 * Merge a Supabase auth user with its `profiles` and `user_roles` rows into
 * the app's `AuthUser` shape. Falls back to safe defaults when the user has
 * no profile/role rows yet.
 */
async function mergeUser(authUser: SupabaseUser): Promise<AuthUser> {
  const profileRes = await supabase
    .from("profiles")
    .select("full_name, initials")
    .eq("id", authUser.id)
    .limit(1)
    .maybeSingle();
  // A profile/role row may be absent, or RLS may deny the read on a fresh
  // account. Never let that throw away a valid session: fall back to safe
  // defaults derived from the verified Supabase user.
  const profile = profileRes.error == null ? (profileRes.data as DbProfile | null) : null;

  const roleRes = await supabase
    .from("user_roles")
    .select("role")
    .eq("user_id", authUser.id)
    .limit(1)
    .maybeSingle();
  const roleRow = roleRes.error == null ? (roleRes.data as DbUserRole | null) : null;

  const name =
    profile?.full_name || authUser.user_metadata?.name || authUser.email?.split("@")[0] || "User";

  const merged: AuthUser = {
    id: authUser.id,
    email: authUser.email ?? "",
    name,
    initials: profile?.initials || initialsFor(name),
    role: roleRow?.role ?? "student",
  };
  return merged;
}

/** Map a Supabase session into the app's Session shape, merging user data. */
export async function mapSession(supabaseSession: SupabaseSession | null): Promise<Session | null> {
  if (!supabaseSession?.access_token || !supabaseSession.user) return null;
  const user = await mergeUser(supabaseSession.user);
  const session: Session = {
    access_token: supabaseSession.access_token,
    refresh_token: supabaseSession.refresh_token,
    expires_at: supabaseSession.expires_at ?? Date.now(),
    user,
  };
  return session;
}

/** Sign in with email + password and return the mapped session. */
export async function login({ email, password }: LoginRequest): Promise<LoginResponse> {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw toError(error, "Wrong email or password.");
  const session = await mapSession(data.session);
  if (!session) throw new Error("Sign-in succeeded but no session was returned.");
  return { session };
}

/** Sign the current user out. */
export async function logout(): Promise<void> {
  const { error } = await supabase.auth.signOut();
  if (error) throw toError(error, "Could not sign out.");
}

/** Refresh the session using the given session's refresh token. */
export async function refreshSession(session: Session): Promise<RefreshSessionResponse> {
  const { data, error } = await supabase.auth.refreshSession({
    refresh_token: session.refresh_token,
  });
  if (error) throw toError(error, "Could not refresh the session.");
  const next = await mapSession(data.session);
  if (!next) throw new Error("Session refresh returned no session.");
  return { session: next };
}

/**
 * Load the current user from Supabase, merging `profiles` and `user_roles`
 * into the `AuthUser` shape. Returns `{ user: null }` when signed out.
 */
export async function getCurrentUser(session?: Session | null): Promise<GetCurrentUserResponse> {
  const { data, error } = await supabase.auth.getUser();
  if (error) throw toError(error, "Could not load the current user.");
  const user = data.user ? await mergeUser(data.user) : null;
  return { user };
}

/** Shape of the demo credentials formerly shown on the login screen. */
export interface DemoAccount {
  email: string;
  password: string;
  role: string;
  name: string;
}

/** Demo accounts are no longer available with Supabase auth. */
export async function listDemoAccounts(): Promise<DemoAccount[]> {
  return [];
}

/** Demo credentials shown on the login screen (Supabase mode: none). */
export function demoAccounts(): DemoAccount[] {
  return [];
}
