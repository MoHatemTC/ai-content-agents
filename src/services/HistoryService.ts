/** History business logic.
 *
 * Since Phase 8 the generation run log lives in **Supabase** (`generations` +
 * `history` tables), not in localStorage. `appendSupabase` is the only writer;
 * reads come from the Supabase `generations`/`history` tables at bootstrap.
 */
import * as historyApi from "@/api/history.api";
import * as supabaseApi from "@/api/supabase.api";
import { supabase } from "@/lib/supabase";
import type { GenerationKind, ReviewStatus } from "@/types/database.types";
import type { ReviewState, WsHistoryRow } from "@/types/domain";

/** Human generator label → Supabase `generation_kind`. */
export const AGENT_TO_KIND: Record<string, GenerationKind> = {
  "Question Bank": "question_bank",
  "Test Help": "test_help",
  Flashcards: "flashcards",
  "Study Plan": "study_plan",
  Revision: "revision_sheet",
};

export const REVIEW_TO_STATUS: Record<ReviewState, ReviewStatus> = {
  Pending: "pending",
  Approved: "approved",
  "Needs Edit": "needs_edit",
  Rejected: "rejected",
};

export const KIND_TO_AGENT: Record<GenerationKind, string> = {
  question_bank: "Question Bank",
  test_help: "Test Help",
  flashcards: "Flashcards",
  study_plan: "Study Plan",
  revision_sheet: "Revision",
};

/** Extra context a generator passes so the run can be persisted to Supabase. */
export interface PersistGenerationMeta {
  kind: GenerationKind;
  model: string;
  /** Human title stored on the generations row (defaults to `agent · doc`). */
  title?: string;
  /** Full generator payload (questions / flashcards / days / weakTopics…). */
  payload?: unknown;
  documentIds?: string[];
  groundingScore?: number | null;
  qualityScore?: number | null;
  /** Persisted generation id; created here when omitted. */
  generationId?: string;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

export const HistoryService = {
  async list(workspaceId: string): Promise<WsHistoryRow[]> {
    return (await historyApi.getHistory({ workspaceId })).history;
  },

  /** Builds the row a generator writes back to workspace history. */
  buildRow(input: {
    agent: string;
    doc: string;
    items: number;
    quality?: number;
    chatId?: string;
    generationId?: string;
  }): WsHistoryRow {
    return {
      id: input.generationId ?? `gen-${Date.now().toString(36)}`,
      date: new Date().toISOString().slice(0, 16).replace("T", " "),
      agent: input.agent,
      doc: input.doc,
      status: "Completed",
      quality: input.quality ?? 9.2,
      review: "Pending",
      items: input.items,
      chatId: input.chatId,
      generationId: input.generationId,
    };
  },

  /**
   * Persist a generation run to Supabase: insert the `generations` row (full
   * payload) then the linked `history` row, both with the signed-in user's id
   * (RLS scopes them to that user's workspace). Returns the generation id, or
   * `null` when there is no signed-in user.
   */
  async appendSupabase(
    workspaceId: string,
    row: WsHistoryRow,
    meta: PersistGenerationMeta,
  ): Promise<string | null> {
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return null;

    const generationId = meta.generationId ?? crypto.randomUUID();
    const kind = meta.kind;
    const status: ReviewStatus = REVIEW_TO_STATUS[row.review] ?? "pending";

    await supabaseApi.insertGeneration({
      id: generationId,
      workspace_id: workspaceId,
      created_by: user.id,
      kind,
      model: meta.model,
      title: meta.title || `${row.agent} · ${row.doc}`,
      payload: meta.payload ?? {},
      document_ids: (meta.documentIds ?? []).filter(isUuid),
      grounding_score: meta.groundingScore ?? null,
      quality_score: meta.qualityScore ?? row.quality,
      review_status: status,
    });

    await supabaseApi.insertHistoryRow({
      id: crypto.randomUUID(),
      workspace_id: workspaceId,
      user_id: user.id,
      generation_id: generationId,
      kind,
      title: `${row.agent} · ${row.doc}`,
      model: meta.model,
      review_status: status,
    });

    return generationId;
  },

  /** Legacy FastAPI writer — kept for the mock path. */
  append: historyApi.appendHistory,
};
