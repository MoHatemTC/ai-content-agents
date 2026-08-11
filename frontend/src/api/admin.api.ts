/** Admin dashboard endpoints. */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import { documents as seedDocuments, analyticsSummary } from "@/mock/mock-data";
import type { AdminStats } from "@/types/api/admin.contracts";

/** Snake_case wire shape returned by the backend. */
interface AdminStatsWire {
  documents: number;
  chunks_indexed: number;
  workspaces: number;
  users: number;
  questions: number;
  flashcards: number;
  study_plans: number;
  quality: number | null;
  recent_documents: Array<{
    id: string;
    title: string;
    kind: string;
    pages: number | null;
    chunks: number;
    status: string;
  }>;
}

function toAdminStats(raw: AdminStatsWire): AdminStats {
  return {
    documents: raw.documents,
    chunksIndexed: raw.chunks_indexed,
    workspaces: raw.workspaces,
    users: raw.users,
    questions: raw.questions,
    flashcards: raw.flashcards,
    studyPlans: raw.study_plans,
    quality: raw.quality,
    recentDocuments: raw.recent_documents.map((d) => ({
      id: d.id,
      title: d.title,
      kind: d.kind,
      pages: d.pages,
      chunks: d.chunks,
      status: d.status,
    })),
  };
}

/** GET /admin/stats — live site-wide totals (staff only). */
export async function getAdminStats(): Promise<AdminStats> {
  if (!isMockMode()) {
    const raw = await http.get<AdminStatsWire>(paths.admin.stats);
    return toAdminStats(raw);
  }
  await delay(160);
  return {
    documents: seedDocuments.length,
    chunksIndexed: seedDocuments.reduce((n, d) => n + d.chunks, 0),
    workspaces: 8,
    users: 6,
    questions: analyticsSummary.questions,
    flashcards: analyticsSummary.flashcards,
    studyPlans: analyticsSummary.studyPlans,
    quality: analyticsSummary.quality,
    recentDocuments: seedDocuments.slice(0, 5).map((d) => ({
      id: d.id,
      title: d.title,
      kind: d.kind,
      pages: d.pages,
      chunks: d.chunks,
      status: d.status,
    })),
  };
}
