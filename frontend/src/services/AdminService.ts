/** Admin dashboard aggregates — live, staff-wide numbers. */
import * as adminApi from "@/api/admin.api";
import * as supabaseApi from "@/api/supabase.api";
import { isMockMode } from "@/config/env";
import { attempt } from "@/lib/result";
import { KIND_TO_AGENT } from "@/services/HistoryService";
import type { Result } from "@/types/api/common";
import type { AdminStats } from "@/types/api/admin.contracts";
import type { DbGeneration } from "@/types/database.types";
import type { ReviewState } from "@/types/domain";

export interface AdminOverview {
  /** Documents across every workspace (staff-wide). */
  documents: number;
  /** Generated question items across all question/test-help generations. */
  questions: number;
  /** Mean grounding score (0–100), null when nothing is scored yet. */
  grounding: number | null;
  /** Mean quality score (0–10), null when nothing is scored yet. */
  quality: number | null;
}

export interface AdminPipelineStats {
  /** Total indexed chunks across every workspace (live count). */
  chunksIndexed: number;
  avgRetrievalMs: number | null;
  topK: number | null;
  embeddingModel: string | null;
  validationPassRate: number | null;
  supportCheckedPct: number | null;
}

/** A Supabase generation formatted for the admin "Recent generations" feed. */
export interface AdminRecentGeneration {
  id: string;
  agent: string;
  items: number;
  doc: string;
  date: string;
  review: ReviewState;
}

/** Number of items carried by a generation payload (questions/flashcards/days/weakTopics). */
function payloadItemCount(g: DbGeneration): number {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  for (const key of ["questions", "flashcards", "days", "weakTopics"]) {
    const value = payload[key];
    if (Array.isArray(value)) return value.length;
  }
  return 0;
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export const AdminService = {
  /**
   * Live platform totals for the admin dashboard. Real mode reads FastAPI
   * `/admin/stats` (site-wide counts from the platform database) for
   * documents/questions/quality and Supabase `generations` (staff-wide) for
   * grounding; mock mode returns the demo figures.
   */
  async stats(): Promise<Result<AdminStats>> {
    return attempt("AdminService.stats", () => adminApi.getAdminStats());
  },

  async overview(): Promise<Result<AdminOverview>> {
    return attempt("AdminService.overview", async () => {
      if (isMockMode()) {
        const stats = await adminApi.getAdminStats();
        return {
          documents: stats.documents,
          questions: stats.questions,
          grounding: 98.4,
          quality: stats.quality,
        };
      }
      const [stats, generations] = await Promise.all([
        adminApi.getAdminStats(),
        supabaseApi.listAllGenerations(),
      ]);
      const grounding = mean(
        generations.map((g) => g.grounding_score).filter((v): v is number => v != null),
      );
      return {
        documents: stats.documents,
        questions: stats.questions,
        grounding: grounding != null ? Math.round(grounding * 10) / 10 : null,
        quality: stats.quality,
      };
    });
  },

  /**
   * Live RAG pipeline telemetry for the /pipeline page. Real mode takes the
   * chunks count from FastAPI `/admin/stats` (the platform database owns the
   * indexed chunks) and the config/measured values from the staff-gated
   * Supabase `pipeline_stats` view; mock mode returns the demo figures.
   */
  async pipelineStats(): Promise<Result<AdminPipelineStats>> {
    return attempt("AdminService.pipelineStats", async () => {
      if (isMockMode()) {
        return {
          chunksIndexed: 990,
          avgRetrievalMs: 184,
          topK: 8,
          embeddingModel: "gemini-embedding-001",
          validationPassRate: 97.2,
          supportCheckedPct: 100,
        };
      }
      const [stats, telemetry] = await Promise.all([
        adminApi.getAdminStats(),
        supabaseApi.getPipelineStats(),
      ]);
      return {
        chunksIndexed: stats.chunksIndexed,
        avgRetrievalMs: telemetry?.avg_retrieval_ms ?? null,
        topK: telemetry?.top_k ?? null,
        embeddingModel: telemetry?.embedding_model ?? null,
        validationPassRate: telemetry?.validation_pass_rate ?? null,
        supportCheckedPct: telemetry?.support_checked_pct ?? null,
      };
    });
  },

  /**
   * Recent generations for the admin dashboard feed. Real mode reads the
   * Supabase `generations` table (staff-wide); mock mode returns the seeded
   * demo history.
   */
  async recentGenerations(): Promise<Result<AdminRecentGeneration[]>> {
    return attempt("AdminService.recentGenerations", async () => {
      if (isMockMode()) {
        const { history } = await import("@/mock/mock-data");
        return history.slice(0, 5).map((h) => ({
          id: h.id,
          agent: h.agent,
          items: h.items,
          doc: h.doc,
          date: h.date,
          review: h.review,
        }));
      }
      const generations = await supabaseApi.listAllGenerations();
      return generations.slice(0, 5).map((g) => ({
        id: g.id,
        agent: KIND_TO_AGENT[g.kind] ?? g.kind,
        items: payloadItemCount(g),
        doc: g.title,
        date: g.created_at.slice(0, 10),
        review: REVIEW_TO_STATUS_REVERSE[g.review_status],
      }));
    });
  },
};

/** Supabase review status → human review state for the admin feed. */
const REVIEW_TO_STATUS_REVERSE: Record<DbGeneration["review_status"], ReviewState> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_edit: "Needs Edit",
};
