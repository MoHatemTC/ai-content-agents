import type { ReviewState } from "@/types/domain";
import type { WsAuditEntry } from "@/types/domain";

export interface ReviewRequest {
  workspaceId: string;
  itemId: string;
  comment?: string;
  /** Human-readable label used in the audit trail. */
  label?: string;
}

export interface ReviewResponse {
  itemId: string;
  status: ReviewState;
  audit: WsAuditEntry;
}

export interface GetReviewQueueResponse {
  itemIds: string[];
}

/**
 * A persisted generated output returned by `GET /review/items`.
 *
 * `status` is the backend's review state (`pending` | `approved` | `rejected`
 * | `edited ...`); `payload` carries the generated content (e.g. `questions`).
 * This is the reload-safe list the review UI reads from instead of local state.
 */
export interface ReviewItem {
  id: string;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface GetReviewItemsResponse {
  items: ReviewItem[];
}

export interface GetAuditHistoryResponse {
  audit: WsAuditEntry[];
}
