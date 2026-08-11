/**
 * Global notification system.
 *
 * The ONLY way the app surfaces feedback. Components call
 * `useNotify()` (or the `notify` singleton outside React) — never `alert`,
 * `console.log` or `toast` directly.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { toast } from "sonner";
import type { ApiError } from "@/types/api/common";

export interface NotifyOptions {
  description?: string;
}

export interface Notifier {
  success: (message: string, options?: NotifyOptions) => void;
  error: (message: string, options?: NotifyOptions) => void;
  warning: (message: string, options?: NotifyOptions) => void;
  info: (message: string, options?: NotifyOptions) => void;
  /** Surfaces a failed `Result` envelope with its code for debuggability. */
  fromError: (error: ApiError, fallback?: string) => void;
}

export const notify: Notifier = {
  success: (message, options) => toast.success(message, options),
  error: (message, options) => toast.error(message, options),
  warning: (message, options) => toast.warning(message, options),
  info: (message, options) => toast.info(message, options),
  fromError: (error, fallback = "Something went wrong.") =>
    toast.error(error.message || fallback, { description: `code: ${error.code}` }),
};

const Ctx = createContext<Notifier>(notify);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const value = useMemo(() => notify, []);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useNotify(): Notifier {
  return useContext(Ctx);
}
