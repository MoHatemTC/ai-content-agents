/**
 * Admin dashboard contracts.
 *
 * Backed by GET /admin/stats (FastAPI) in real mode — live site-wide totals
 * computed from the platform database.
 */

/** A document row in the admin library snapshot. */
export interface AdminRecentDocument {
  id: string;
  title: string;
  kind: string;
  pages: number | null;
  chunks: number;
  status: string;
}

/** Live site-wide totals for the admin dashboard. */
export interface AdminStats {
  documents: number;
  chunksIndexed: number;
  workspaces: number;
  users: number;
  questions: number;
  flashcards: number;
  studyPlans: number;
  quality: number | null;
  recentDocuments: AdminRecentDocument[];
}
