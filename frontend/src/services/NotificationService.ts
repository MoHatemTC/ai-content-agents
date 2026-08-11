/** Notification feed business logic (in-app notification centre). */
import * as catalogueApi from "@/api/catalogue.api";
import * as supabaseApi from "@/api/supabase.api";
import { isMockMode } from "@/config/env";
import { attempt } from "@/lib/result";
import type { ListNotificationsResponse } from "@/types/api/catalogue.contracts";
import type { Result } from "@/types/api/common";
import type { AppNotification, NotificationKind } from "@/types/domain";
import type { DbNotification, UserRole } from "@/types/database.types";

/** Map a Supabase row onto the UI notification model. */
function rowToNotification(row: DbNotification): AppNotification {
  const kind = (
    ["review", "validation", "export", "grounding", "done"].includes(row.kind) ? row.kind : "done"
  ) as NotificationKind;
  return {
    id: row.id,
    kind,
    title: row.title,
    detail: row.body,
    time: (row.created_at ?? "").slice(0, 16).replace("T", " "),
    unread: !row.read,
    roles: (row.roles?.length ? row.roles : ["student", "reviewer", "admin"]) as Array<
      "student" | "reviewer" | "admin"
    >,
  };
}

export const NotificationService = {
  async list(role?: UserRole): Promise<Result<ListNotificationsResponse>> {
    return attempt("NotificationService.list", async () => {
      if (isMockMode()) return catalogueApi.getNotifications({ role });
      // RLS filters the rows to this user (own + staff role rows).
      const rows = await supabaseApi.listNotifications();
      const notifications = rows.map(rowToNotification);
      return { notifications, unread: notifications.filter((n) => n.unread).length };
    });
  },

  async markRead(id: string): Promise<Result<{ id: string }>> {
    return attempt("NotificationService.markRead", async () => {
      if (isMockMode()) return catalogueApi.markNotificationRead(id);
      await supabaseApi.markNotificationRead(id);
      return { id };
    });
  },

  async markAllRead(): Promise<Result<{ updated: number }>> {
    return attempt("NotificationService.markAllRead", async () => {
      if (isMockMode()) return catalogueApi.markAllNotificationsRead();
      return { updated: await supabaseApi.markAllNotificationsRead() };
    });
  },

  /** Subscribe to new notification rows (real mode). Returns an unsubscribe fn. */
  subscribe(onChange: () => void): (() => void) | null {
    if (isMockMode()) return null;
    return supabaseApi.subscribeNotifications(onChange);
  },
};
