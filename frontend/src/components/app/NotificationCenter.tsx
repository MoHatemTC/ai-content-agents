import { useEffect } from "react";
import { Bell, CheckCheck, Download, ShieldAlert, ShieldX, Sparkles, Inbox } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/AsyncState";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { NotificationService } from "@/services";
import { unwrap } from "@/lib/result";
import { useNotify } from "@/contexts/NotificationContext";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import type { NotificationKind } from "@/types/domain";

const kindIcon: Record<NotificationKind, React.ComponentType<{ className?: string }>> = {
  review: Inbox,
  validation: ShieldAlert,
  export: Download,
  grounding: ShieldX,
  done: Sparkles,
};

const kindTone: Record<NotificationKind, string> = {
  review: "bg-warning/12 text-warning",
  validation: "bg-info/12 text-info",
  export: "bg-success/12 text-success",
  grounding: "bg-destructive/12 text-destructive",
  done: "bg-primary/12 text-primary",
};

export function NotificationCenter() {
  const { user } = useAuth();
  const notify = useNotify();
  const queryClient = useQueryClient();

  const { data, isPending, error, refetch } = useServiceQuery(
    ["notifications", user?.id, user?.role],
    () => NotificationService.list(user?.role),
    { enabled: Boolean(user) },
  );

  const markAll = useMutation({
    mutationFn: () => unwrap(NotificationService.markAllRead()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      notify.success("All notifications marked as read");
    },
    onError: (err: Error) =>
      notify.error("Could not update notifications", { description: err.message }),
  });

  // Realtime: when a notification row the current user may read is inserted,
  // refetch the feed so new activity appears without a manual refresh.
  useEffect(() => {
    if (!user) return;
    const unsubscribe = NotificationService.subscribe(() => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    });
    return () => {
      unsubscribe?.();
    };
  }, [user?.id, queryClient]);

  const items = data?.notifications ?? [];
  const unread = data?.unread ?? 0;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
          <Bell className="size-4.5" />
          {unread > 0 && (
            <span className="bg-primary text-primary-foreground absolute top-1 right-1 flex size-4 items-center justify-center rounded-full text-[10px] font-semibold">
              {unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-88 p-0">
        <div className="flex items-center justify-between px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          <button
            disabled={markAll.isPending || items.length === 0}
            onClick={() => markAll.mutate()}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs disabled:opacity-50"
          >
            <CheckCheck className="size-3.5" /> Mark all read
          </button>
        </div>

        <div className="border-border max-h-96 overflow-y-auto border-t">
          {isPending && <LoadingState label="Loading notifications…" className="py-8" />}
          {!isPending && error && (
            <ErrorState
              title="Unable to load notifications"
              message={error.message}
              onRetry={() => void refetch()}
              className="py-8"
            />
          )}
          {!isPending && !error && items.length === 0 && (
            <EmptyState
              title="Nothing here yet"
              message="New activity will show up here."
              className="py-8"
            />
          )}
          {!isPending && !error && items.length > 0 && (
            <ul className="border-border divide-y">
              {items.map((n) => {
                const Icon = kindIcon[n.kind];
                return (
                  <li
                    key={n.id}
                    className={cn(
                      "hover:bg-muted/50 flex gap-3 px-4 py-3",
                      n.unread && "bg-primary/4",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-8 shrink-0 items-center justify-center rounded-xl",
                        kindTone[n.kind],
                      )}
                    >
                      <Icon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{n.title}</p>
                      <p className="text-muted-foreground truncate text-xs">{n.detail}</p>
                    </div>
                    <span className="text-muted-foreground shrink-0 text-[11px]">{n.time}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
