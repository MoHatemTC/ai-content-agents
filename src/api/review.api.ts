/** Review endpoints — approve / reject / needs-edit / comment plus audit trail. */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import type { ReviewState } from "@/types/domain";
import type { WsAuditEntry } from "@/types/domain";
import type {
  GetAuditHistoryResponse,
  GetReviewItemsResponse,
  GetReviewQueueResponse,
  ReviewRequest,
  ReviewResponse,
} from "@/types/api/review.contracts";

function audit(req: ReviewRequest, action: WsAuditEntry["action"], actor: string): WsAuditEntry {
  return {
    id: `aud-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    itemId: req.itemId,
    itemLabel: req.label ?? req.itemId,
    action,
    actor,
    at: new Date().toISOString().slice(0, 16).replace("T", " "),
    comment: req.comment,
  };
}

async function submit(
  path: string,
  req: ReviewRequest,
  status: ReviewState,
  action: WsAuditEntry["action"],
  actor: string,
): Promise<ReviewResponse> {
  if (!isMockMode()) return http.post<ReviewResponse>(path, req);
  await delay(80);
  return { itemId: req.itemId, status, audit: audit(req, action, actor) };
}

export const approveGeneration = (req: ReviewRequest, actor = "You") =>
  submit(paths.review.approve, req, "Approved", "Approved", actor);

export const rejectGeneration = (req: ReviewRequest, actor = "You") =>
  submit(paths.review.reject, req, "Rejected", "Rejected", actor);

export const requestEdits = (req: ReviewRequest, actor = "You") =>
  submit(paths.review.needsEdit, req, "Needs Edit", "Needs Edit", actor);

export const flagGeneration = (req: ReviewRequest, actor = "System") =>
  submit(paths.review.flag, req, "Pending", "Flagged", actor);

export const commentOnGeneration = (req: ReviewRequest, actor = "You") =>
  submit(paths.review.comment, req, "Pending", "Comment", actor);

export async function getReviewQueue(workspaceId: string): Promise<GetReviewQueueResponse> {
  if (!isMockMode())
    return http.get<GetReviewQueueResponse>(`${paths.review.queue}?workspace_id=${workspaceId}`);
  const { getWorkspaceData } = await import("./workspace.api");
  const data = await getWorkspaceData(workspaceId);
  return { itemIds: data.questions.filter((q) => q.review === "Pending").map((q) => q.id) };
}

/** Load generated output items (with content) for a workspace — reload-safe. */
export async function getReviewItems(workspaceId: string): Promise<GetReviewItemsResponse> {
  if (!isMockMode())
    return http.get<GetReviewItemsResponse>(`${paths.review.items}?workspace_id=${workspaceId}`);
  const { getWorkspaceData } = await import("./workspace.api");
  const data = await getWorkspaceData(workspaceId);
  return {
    items: data.questions.map((q) => ({
      id: q.id,
      kind: "question_bank",
      status: q.review.toLowerCase().replace(" ", "_"),
      payload: { questions: [q] },
      created_at: "",
    })),
  };
}

export async function getAuditHistory(workspaceId: string): Promise<GetAuditHistoryResponse> {
  if (!isMockMode()) {
    return http.get<GetAuditHistoryResponse>(`${paths.review.audit}?workspace_id=${workspaceId}`);
  }
  const { getWorkspaceData } = await import("./workspace.api");
  const data = await getWorkspaceData(workspaceId);
  return { audit: data.audit ?? [] };
}
