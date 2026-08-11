/** Shared request/response envelope types for the FastAPI backend. */

/** JSON-serializable value — used instead of `unknown` for error details. */
export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface ApiError {
  code: string;
  message: string;
  details?: JsonValue;
}

export interface ApiResponse<T> {
  data: T;
  error?: ApiError | null;
}

/**
 * The single shape every service method resolves to. Services never throw.
 */
export type Result<T> = { success: true; data: T } | { success: false; error: ApiError };

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginationQuery {
  page?: number;
  page_size?: number;
}
