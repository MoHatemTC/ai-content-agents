/**
 * Thin HTTP client for the FastAPI backend.
 *
 * Every `*.api.ts` module routes network access through here, so auth headers,
 * base URL and error shaping live in exactly one place. While
 * `env.ENABLE_MOCK` is on, the api modules short-circuit and never reach this
 * client.
 */
import { env } from "@/config/env";
import type { ApiError } from "@/types/api/common";

let accessToken: string | null = null;

/** Maximum time a request may run before it is aborted. */
const DEFAULT_TIMEOUT_MS = 90_000;

/** Normalized API base URL (no trailing slash) used to build request URLs. */
const BASE_URL = env.API_BASE_URL.replace(/\/+$/, "");

/** Called by AuthService whenever a session is created/refreshed/cleared. */
export function setAccessToken(token: string | null) {
  accessToken = token;
}

export class HttpError extends Error {
  status: number;
  body: ApiError | null;
  constructor(status: number, message: string, body: ApiError | null) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...((init?.headers as Record<string, string>) ?? {}),
  };

  // When the caller does not manage its own signal, enforce a request timeout
  // so a stalled backend cannot hang the UI indefinitely.
  const hasExternalSignal = init?.signal !== undefined;
  const controller = new AbortController();
  const timer = hasExternalSignal
    ? undefined
    : setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      method,
      headers,
      signal: init?.signal ?? controller.signal,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  } catch (error) {
    if (!hasExternalSignal && error instanceof Error && error.name === "AbortError") {
      throw new Error(`Request timed out after ${DEFAULT_TIMEOUT_MS / 1000}s.`);
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }

  const payload = res.status === 204 ? null : await res.json().catch(() => null);

  if (!res.ok) {
    const err = (payload as { error?: ApiError } | null)?.error ?? null;
    throw new HttpError(res.status, err?.message ?? res.statusText, err);
  }

  return (payload as { data?: T })?.data !== undefined
    ? ((payload as { data: T }).data as T)
    : (payload as T);
}

export const http = {
  get: <T>(path: string, init?: RequestInit) => request<T>("GET", path, undefined, init),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("POST", path, body, init),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  /**
   * POST a JSON body and receive a binary file (e.g. an exported document) with
   * the current auth header, returning the Blob and the server filename.
   */
  async download(
    path: string,
    body?: unknown,
    init?: RequestInit,
  ): Promise<{ blob: Blob; filename: string }> {
    const headers: Record<string, string> = {
      Accept: "application/octet-stream, application/json",
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...((init?.headers as Record<string, string>) ?? {}),
    };
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      method: "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as { error?: ApiError } | null;
      throw new HttpError(res.status, err?.error?.message ?? res.statusText, err?.error ?? null);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = /filename="?([^";]+)"?/.exec(disposition);
    const filename = match?.[1] ?? "download";
    return { blob, filename };
  },
};

/** Simulated latency so mock responses behave like real async calls. */
export const delay = (ms = 220) => new Promise<void>((resolve) => setTimeout(resolve, ms));
