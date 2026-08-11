/** Review workflow + permissions. Components never inline role logic. */
import * as reviewApi from "@/api/review.api";
import * as supabaseApi from "@/api/supabase.api";
import { supabase } from "@/lib/supabase";
import type { ReviewState } from "@/types/domain";
import type { WsAuditEntry } from "@/types/domain";
import { ROLE_PERMISSIONS, type Permission } from "@/constants";
import type {
  DbGeneration,
  DbGenerationWithCreator,
  DbReview,
  GenerationKind,
  ReviewStatus,
  UserRole,
} from "@/types/database.types";
import type { ReviewRequest, ReviewResponse } from "@/types/api/review.contracts";

export const REVIEW_STATUS_TO_STATE: Record<ReviewStatus, ReviewState> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_edit: "Needs Edit",
};

/** Number of items a generation payload carries, by kind. */
function payloadItemCount(g: DbGeneration): number {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  for (const key of ["questions", "flashcards", "days", "weakTopics"]) {
    const value = payload[key];
    if (Array.isArray(value)) return value.length;
  }
  return 0;
}

/** Aggregate a generation's review status from per-item decisions. */
function aggregateStatus(total: number, reviews: DbReview[]): ReviewStatus {
  if (total <= 0) return reviews[0]?.status ?? "pending";
  const counts = { rejected: 0, needs_edit: 0, approved: 0 };
  for (const r of reviews) {
    if (r.status === "rejected") counts.rejected++;
    else if (r.status === "needs_edit") counts.needs_edit++;
    else if (r.status === "approved") counts.approved++;
  }
  if (counts.rejected > 0) return "rejected";
  if (counts.needs_edit > 0) return "needs_edit";
  if (counts.approved === total) return "approved";
  return "pending";
}

export const ReviewService = {
  can(role: UserRole | undefined, permission: Permission): boolean {
    if (!role) return false;
    return (ROLE_PERMISSIONS[role] as readonly string[]).includes(permission);
  },

  approve: (req: ReviewRequest, actor?: string) => reviewApi.approveGeneration(req, actor),
  reject: (req: ReviewRequest, actor?: string) => reviewApi.rejectGeneration(req, actor),
  requestEdits: (req: ReviewRequest, actor?: string) => reviewApi.requestEdits(req, actor),
  comment: (req: ReviewRequest, actor?: string) => reviewApi.commentOnGeneration(req, actor),
  flag: (req: ReviewRequest, actor?: string) => reviewApi.flagGeneration(req, actor),

  /** Generic entry point used by the review UI. */
  async setState(state: ReviewState, req: ReviewRequest, actor?: string): Promise<ReviewResponse> {
    if (state === "Approved") return ReviewService.approve(req, actor);
    if (state === "Rejected") return ReviewService.reject(req, actor);
    if (state === "Needs Edit") return ReviewService.requestEdits(req, actor);
    return ReviewService.flag(req, actor);
  },

  async queue(workspaceId: string): Promise<string[]> {
    return (await reviewApi.getReviewQueue(workspaceId)).itemIds;
  },

  async auditHistory(workspaceId: string): Promise<WsAuditEntry[]> {
    return (await reviewApi.getAuditHistory(workspaceId)).audit;
  },

  /** An item is auto-flagged when grounding or quality fall below threshold. */
  shouldAutoFlag(grounded: number, quality: number): boolean {
    return grounded < 98 || quality < 8.5;
  },

  /* ---------------------------------------------------------------------
   * Phase 8 Supabase review queue (the reviewer page reads/writes these).
   * ------------------------------------------------------------------- */

  /**
   * Load the review queue: one workspace (owner path) or every workspace the
   * caller may see (staff path, when `workspaceId` is empty). RLS scopes the
   * staff reads to rows the caller can actually see. Rows carry creator +
   * workspace provenance via `generation_with_creator`.
   */
  async hydrateQueue(workspaceId?: string): Promise<{
    generations: DbGenerationWithCreator[];
    reviews: DbReview[];
  }> {
    const [generations, reviews] = workspaceId
      ? await Promise.all([
          supabaseApi.listGenerationsWithCreator(workspaceId),
          supabaseApi.listReviewsForWorkspace(workspaceId),
        ])
      : await Promise.all([supabaseApi.listGenerationsWithCreator(), supabaseApi.listAllReviews()]);
    return { generations, reviews };
  },

  /**
   * Record a per-item review decision in Supabase and roll the generation's
   * status up from every item's decisions. Returns the new generation status.
   */
  async decideItem(input: {
    generationId: string;
    workspaceId: string;
    itemId: string;
    status: ReviewStatus;
    comment?: string | null;
  }): Promise<ReviewStatus> {
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) throw new Error("You must be signed in to review");
    const generation = await supabaseApi.getGeneration(input.generationId);
    if (!generation) throw new Error("Generation not found");

    await supabaseApi.insertReview({
      id: crypto.randomUUID(),
      generation_id: input.generationId,
      workspace_id: input.workspaceId,
      item_id: input.itemId,
      reviewer_id: user.id,
      status: input.status,
      comment: input.comment ?? null,
    });

    const reviews = await supabaseApi.listReviewsForGeneration(input.generationId);
    const next = aggregateStatus(payloadItemCount(generation), reviews);
    await supabaseApi.setGenerationReviewStatus(input.generationId, next);
    return next;
  },

  /** Reviewable generator kinds that queue on the reviewer page. */
  kinds(): GenerationKind[] {
    return supabaseApi.REVIEWABLE_KINDS;
  },
};
