/**
 * Shared Loading / Error / Empty presentation.
 *
 * Every service-backed view renders through `<AsyncSection>` so the four states
 * (loading, error, empty, success) look and behave identically app-wide.
 */
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function LoadingState({
  label = "Loading…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "text-muted-foreground flex flex-col items-center justify-center gap-3 py-14 text-sm",
        className,
      )}
    >
      <Loader2 className="text-primary size-5 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center gap-3 py-14 text-center", className)}
    >
      <span className="bg-destructive/10 text-destructive flex size-11 items-center justify-center rounded-2xl">
        <AlertTriangle className="size-5" />
      </span>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        {message && <p className="text-muted-foreground mt-1 text-xs">{message}</p>}
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  message,
  action,
  className,
}: {
  title?: string;
  message?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-3 py-14 text-center", className)}
    >
      <span className="bg-muted text-muted-foreground flex size-11 items-center justify-center rounded-2xl">
        <Inbox className="size-5" />
      </span>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        {message && <p className="text-muted-foreground mt-1 text-xs">{message}</p>}
      </div>
      {action}
    </div>
  );
}

/**
 * Content placeholder for routes that are meaningless without an active
 * workspace. The create action lives in the sidebar's workspace switcher, so
 * this is purely informational.
 */
export function NoActiveWorkspace({ className }: { className?: string }) {
  return (
    <EmptyState
      title="No active workspace"
      message="Create your first workspace from the sidebar to get started."
      className={className}
    />
  );
}

export interface AsyncSectionProps<T> {
  isLoading: boolean;
  error?: { message: string } | null;
  data: T | undefined;
  /** Decides whether successfully loaded data should render the empty state. */
  isEmpty?: (data: T) => boolean;
  loadingLabel?: string;
  emptyTitle?: string;
  emptyMessage?: string;
  emptyAction?: ReactNode;
  errorTitle?: string;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}

export function AsyncSection<T>({
  isLoading,
  error,
  data,
  isEmpty,
  loadingLabel,
  emptyTitle,
  emptyMessage,
  emptyAction,
  errorTitle,
  onRetry,
  children,
}: AsyncSectionProps<T>) {
  if (isLoading) return <LoadingState label={loadingLabel} />;
  if (error) return <ErrorState title={errorTitle} message={error.message} onRetry={onRetry} />;
  if (data === undefined)
    return <EmptyState title={emptyTitle} message={emptyMessage} action={emptyAction} />;
  if (isEmpty?.(data))
    return <EmptyState title={emptyTitle} message={emptyMessage} action={emptyAction} />;
  return <>{children(data)}</>;
}
