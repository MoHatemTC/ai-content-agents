/**
 * Central runtime configuration.
 *
 * All values are read from Vite env vars with safe placeholder defaults so the
 * app runs entirely on mock data today. Wiring a real backend later means
 * setting these variables — no code changes.
 */

function readEnv(key: string, fallback: string): string {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  return raw && raw.length > 0 ? raw : fallback;
}

function readBool(key: string, fallback: boolean): boolean {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  if (raw === undefined) return fallback;
  return raw === "true" || raw === "1";
}

export const env = {
  /** FastAPI base URL, e.g. https://api.example.com */
  API_BASE_URL: readEnv("VITE_API_BASE_URL", "/api"),
  /** Supabase project URL (placeholder until Cloud/Supabase is enabled). */
  SUPABASE_URL: readEnv("VITE_SUPABASE_URL", ""),
  /** Supabase publishable/anon key (safe for the browser). */
  SUPABASE_ANON_KEY: readEnv("VITE_SUPABASE_ANON_KEY", ""),
  /** When true, the API layer resolves from `src/mock` instead of the network. */
  ENABLE_MOCK: readBool("VITE_ENABLE_MOCK", true),
  /** Default AI provider id used by the model selector. */
  DEFAULT_MODEL: readEnv("VITE_DEFAULT_MODEL", "gemini"),
} as const;

export type AppEnv = typeof env;

export const isMockMode = () => env.ENABLE_MOCK || env.API_BASE_URL === "/api";
