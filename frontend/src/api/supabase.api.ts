/**
 * Supabase data access for the persistent user-facing store.
 *
 * The FastAPI backend remains the single source of truth for *generation* and
 * *workspace records*; Supabase stores the user-facing artifacts that the
 * review workflow, notifications, reopen-from-history and favorites depend on:
 *
 *   * `generations`        — every successful generation, with its full payload.
 *   * `history`            — the generation run log (linked to `generations`).
 *   * `reviews`            — reviewer/admin decisions per generated item.
 *   * `notifications`      — owner + staff feeds (RLS already scopes visibility).
 *   * `workspaces`         — mirrors of FastAPI workspaces so the FK-linking
 *                            tables above resolve (owner_id == auth.uid()).
 *   * `flashcard_favorites`— per-user card favorites.
 *
 * Every query runs through the shared `supabase` client with the caller's own
 * JWT, so RLS (migrations 001/009/011/013/016) is the actual gate. This module
 * never reads or writes FastAPI data — that stays in `src/api/http.ts` land.
 */
import { supabase } from "@/lib/supabase";
import { logger } from "@/lib/logger";
import type {
  DbGeneration,
  DbGenerationWithCreator,
  DbNotification,
  DbPipelineStats,
  DbReview,
  DbWorkspaceWithOwner,
  FlashcardFavorite,
  GenerationKind,
  ReviewStatus,
} from "@/types/database.types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

/** Kinds that flow into the review queue (all generator agents). */
export const REVIEWABLE_KINDS: GenerationKind[] = [
  "question_bank",
  "flashcards",
  "test_help",
  "study_plan",
  "revision_sheet",
];

/* ---------------------------------------------------------------------------
 * Workspaces (mirror of FastAPI records so FKs + the reviewer view resolve)
 * ------------------------------------------------------------------------- */

export interface WorkspaceMirrorRow {
  id: string;
  owner_id: string;
  name: string;
  subject: string;
  description: string | null;
  accent: string | null;
}

/**
 * Mirror FastAPI workspaces into Supabase (owner-scoped).
 *
 * Insert-only (`ignoreDuplicates`): existing rows are left untouched so a
 * bootstrap never rewrites a row that already exists. Rewriting would fire a
 * `postgres_changes` Realtime event back into the frontend, which invalidates
 * the bootstrap query and refetches — an infinite loop. Renames/deletes are
 * pushed one row at a time via `updateWorkspaceMirror`/`deleteWorkspaceMirror`.
 */
export async function syncWorkspaces(rows: WorkspaceMirrorRow[]): Promise<void> {
  for (const row of rows) {
    // `workspaces.id` is `uuid`; FastAPI ids in any other shape cannot be
    // FK-referenced and would fail the whole batch, so skip them.
    if (!isUuid(row.id)) continue;
    try {
      const { error } = await supabase
        .from("workspaces")
        .upsert(row, { onConflict: "id", ignoreDuplicates: true });
      if (error) throw error;
    } catch (err) {
      // A single non-owner/duplicate row must not break bootstrap; FastAPI
      // remains the source of truth for workspace records. Log it so a missing
      // mirror is visible instead of silently breaking generation persistence.
      logger.warn(
        `Workspace mirror skipped: ${row.id}`,
        err instanceof Error ? err.message : String(err),
      );
    }
  }
}

/** Push a single workspace rename/description change into the Supabase mirror. */
export async function updateWorkspaceMirror(
  id: string,
  patch: { name?: string; description?: string | null; subject?: string },
): Promise<void> {
  const { error } = await supabase.from("workspaces").update(patch).eq("id", id);
  if (error) throw error;
}

/** Remove the Supabase mirror row so it cannot linger after a FastAPI delete. */
export async function deleteWorkspaceMirror(id: string): Promise<void> {
  const { error } = await supabase.from("workspaces").delete().eq("id", id);
  if (error) throw error;
}

/** Every workspace the caller may see (staff: all; owner: own) with owner info. */
export async function listWorkspacesWithOwner(): Promise<DbWorkspaceWithOwner[]> {
  const { data, error } = await supabase
    .from("workspace_with_owner")
    .select("*")
    .order("updated_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as DbWorkspaceWithOwner[];
}

/* ---------------------------------------------------------------------------
 * Generations + history
 * ------------------------------------------------------------------------- */

export interface InsertGenerationInput {
  id: string;
  workspace_id: string;
  created_by: string;
  kind: GenerationKind;
  model: string;
  title: string;
  payload: unknown;
  document_ids: string[];
  grounding_score: number | null;
  quality_score: number | null;
  review_status: ReviewStatus;
}

export async function insertGeneration(input: InsertGenerationInput): Promise<void> {
  const { error } = await supabase.from("generations").insert(input);
  if (error) throw error;
}

export async function insertHistoryRow(input: {
  id: string;
  workspace_id: string;
  user_id: string;
  generation_id: string;
  kind: GenerationKind;
  title: string;
  model: string;
  review_status: ReviewStatus;
}): Promise<void> {
  const { error } = await supabase.from("history").insert(input);
  if (error) throw error;
}

export async function getGeneration(id: string): Promise<DbGeneration | null> {
  const { data, error } = await supabase.from("generations").select("*").eq("id", id).maybeSingle();
  if (error) throw error;
  return (data ?? null) as DbGeneration | null;
}

export async function listWorkspaceGenerations(
  workspaceId: string,
  kinds: GenerationKind[] = REVIEWABLE_KINDS,
): Promise<DbGeneration[]> {
  const { data, error } = await supabase
    .from("generations")
    .select("*")
    .eq("workspace_id", workspaceId)
    .in("kind", kinds)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as DbGeneration[];
}

/** All generations the caller may see — staff (reviewer/admin) see every row. */
export async function listAllGenerations(
  kinds: GenerationKind[] = REVIEWABLE_KINDS,
): Promise<DbGeneration[]> {
  const { data, error } = await supabase
    .from("generations")
    .select("*")
    .in("kind", kinds)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as DbGeneration[];
}

/**
 * Generations with creator + workspace provenance, filtered to the caller's
 * visibility (staff: every row; owner: their own) by the security-definer view.
 */
export async function listGenerationsWithCreator(
  workspaceId?: string,
  kinds: GenerationKind[] = REVIEWABLE_KINDS,
): Promise<DbGenerationWithCreator[]> {
  let query = supabase
    .from("generation_with_creator")
    .select("*")
    .in("kind", kinds)
    .order("created_at", { ascending: false });
  if (workspaceId) query = query.eq("workspace_id", workspaceId);
  const { data, error } = await query;
  if (error) throw error;
  return (data ?? []) as DbGenerationWithCreator[];
}

export async function listGenerationsForWorkspaces(
  workspaceIds: string[],
): Promise<DbGeneration[]> {
  const ids = workspaceIds.filter(isUuid);
  if (ids.length === 0) return [];
  const { data, error } = await supabase
    .from("generations")
    .select("*")
    .in("workspace_id", ids)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as DbGeneration[];
}

export async function setGenerationReviewStatus(id: string, status: ReviewStatus): Promise<void> {
  const { error } = await supabase
    .from("generations")
    .update({ review_status: status })
    .eq("id", id);
  if (error) throw error;
}

/* ---------------------------------------------------------------------------
 * Reviews
 * ------------------------------------------------------------------------- */

export interface InsertReviewInput {
  id: string;
  generation_id: string;
  workspace_id: string;
  item_id: string;
  reviewer_id: string;
  status: ReviewStatus;
  comment: string | null;
}

export async function insertReview(input: InsertReviewInput): Promise<void> {
  const { error } = await supabase.from("reviews").upsert(input, {
    onConflict: "generation_id,item_id",
  });
  if (error) throw error;
}

export async function listReviewsForWorkspace(workspaceId: string): Promise<DbReview[]> {
  const { data, error } = await supabase
    .from("reviews")
    .select("*")
    .eq("workspace_id", workspaceId)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return (data ?? []) as DbReview[];
}

/** All reviews the caller may see — staff (reviewer/admin) see every row. */
export async function listAllReviews(): Promise<DbReview[]> {
  const { data, error } = await supabase
    .from("reviews")
    .select("*")
    .order("created_at", { ascending: true });
  if (error) throw error;
  return (data ?? []) as DbReview[];
}

export async function listReviewsForGeneration(generationId: string): Promise<DbReview[]> {
  const { data, error } = await supabase
    .from("reviews")
    .select("*")
    .eq("generation_id", generationId)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return (data ?? []) as DbReview[];
}

/* ---------------------------------------------------------------------------
 * Notifications
 * ------------------------------------------------------------------------- */

export async function listNotifications(): Promise<DbNotification[]> {
  const { data, error } = await supabase
    .from("notifications")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(50);
  if (error) throw error;
  return (data ?? []) as DbNotification[];
}

export async function markNotificationRead(id: string): Promise<void> {
  const { error } = await supabase.from("notifications").update({ read: true }).eq("id", id);
  if (error) throw error;
}

export async function markAllNotificationsRead(): Promise<number> {
  const { data, error } = await supabase
    .from("notifications")
    .update({ read: true })
    .eq("read", false)
    .select("id");
  if (error) throw error;
  return (data ?? []).length;
}

/**
 * Subscribe to new notifications for the current user. RLS filters every
 * delivered change to what this user may read (own rows + staff role rows).
 * Returns an unsubscribe function.
 */
export function subscribeNotifications(onChange: () => void): () => void {
  const channel = supabase
    .channel("notifications-feed")
    .on("postgres_changes", { event: "INSERT", schema: "public", table: "notifications" }, () =>
      onChange(),
    )
    .subscribe();
  return () => {
    void supabase.removeChannel(channel);
  };
}

/* ---------------------------------------------------------------------------
 * Flashcard favorites
 * ------------------------------------------------------------------------- */

export async function listFlashcardFavorites(workspaceId?: string): Promise<FlashcardFavorite[]> {
  let query = supabase
    .from("flashcard_favorites")
    .select("*")
    .order("created_at", { ascending: false });
  if (workspaceId) query = query.eq("workspace_id", workspaceId);
  const { data, error } = await query;
  if (error) throw error;
  return (data ?? []) as FlashcardFavorite[];
}

export async function addFlashcardFavorite(input: {
  user_id: string;
  generation_id: string | null;
  workspace_id: string | null;
  front: string;
  back: string | null;
  topic: string | null;
  format: string | null;
  source_chunk_id: string | null;
}): Promise<void> {
  const { error } = await supabase.from("flashcard_favorites").upsert(input, {
    onConflict: "user_id,front",
  });
  if (error) throw error;
}

export async function removeFlashcardFavorite(userId: string, front: string): Promise<void> {
  const { error } = await supabase
    .from("flashcard_favorites")
    .delete()
    .eq("user_id", userId)
    .eq("front", front);
  if (error) throw error;
}

/* ---------------------------------------------------------------------------
 * Pipeline telemetry (migration 019 — staff-gated pipeline_stats view)
 * ------------------------------------------------------------------------- */

export async function getPipelineStats(): Promise<DbPipelineStats | null> {
  const { data, error } = await supabase.from("pipeline_stats").select("*").limit(1).maybeSingle();
  if (error) throw error;
  return (data ?? null) as DbPipelineStats | null;
}
