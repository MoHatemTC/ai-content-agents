/**
 * Bridges the `Result<T>` service contract to TanStack Query.
 *
 * Services never throw; `unwrap` turns a failed envelope into a `ServiceError`
 * so Query owns the error state and every page gets loading/error/empty for free.
 */
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { unwrap, ServiceError } from "@/lib/result";
import type { Result } from "@/types/api/common";

export function useServiceQuery<T>(
  queryKey: readonly unknown[],
  fetcher: () => Promise<Result<T>>,
  options?: Omit<UseQueryOptions<T, ServiceError>, "queryKey" | "queryFn">,
) {
  return useQuery<T, ServiceError>({
    queryKey,
    queryFn: () => unwrap(fetcher()),
    ...options,
  });
}
