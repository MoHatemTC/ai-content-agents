/**
 * Standard service result envelope.
 *
 * Every `*Service` method resolves to `Result<T>` — never throws, never returns
 * a bare value. Callers branch on `success` so error handling is uniform and
 * debuggable.
 */
import { HttpError } from "@/api/http";
import type { ApiError, Result } from "@/types/api/common";
import { logger } from "./logger";

export function ok<T>(data: T): Result<T> {
  return { success: true, data };
}

export function fail<T = never>(
  code: string,
  message: string,
  details?: ApiError["details"],
): Result<T> {
  return { success: false, error: { code, message, details } };
}

/** Error codes the UI can branch on. Keep in sync with the FastAPI error codes. */
export const ERROR_CODES = {
  network: "network_error",
  unauthorized: "unauthorized",
  forbidden: "forbidden",
  notFound: "not_found",
  validation: "validation_error",
  unknown: "unknown_error",
} as const;

function codeForStatus(status: number): string {
  if (status === 401) return ERROR_CODES.unauthorized;
  if (status === 403) return ERROR_CODES.forbidden;
  if (status === 404) return ERROR_CODES.notFound;
  if (status === 422 || status === 400) return ERROR_CODES.validation;
  return ERROR_CODES.unknown;
}

/**
 * Wraps an api call so transport/unexpected errors become a typed failure
 * instead of a thrown value.
 */
export async function attempt<T>(op: string, fn: () => Promise<T>): Promise<Result<T>> {
  try {
    return ok(await fn());
  } catch (error) {
    if (error instanceof HttpError) {
      logger.error(`${op} failed`, error);
      return fail(error.body?.code ?? codeForStatus(error.status), error.message);
    }
    const message = error instanceof Error ? error.message : `${op} failed unexpectedly.`;
    logger.error(`${op} failed`, message);
    return fail(ERROR_CODES.unknown, message);
  }
}

/**
 * Reads a result inside a TanStack Query `queryFn`, where Query itself owns the
 * error state. Keeps the envelope as the single source of error truth.
 */
export async function unwrap<T>(result: Promise<Result<T>>): Promise<T> {
  const res = await result;
  if (res.success) return res.data;
  throw new ServiceError(res.error);
}

export class ServiceError extends Error {
  code: string;
  constructor(error: ApiError) {
    super(error.message);
    this.name = "ServiceError";
    this.code = error.code;
  }
}
