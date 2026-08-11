/**
 * Expected database shape (Supabase/Postgres).
 *
 * These interfaces are the contract between the frontend and the future
 * database. They intentionally use snake_case column names so they can be
 * mapped 1:1 onto Supabase rows / FastAPI ORM models.
 */

export type UserRole = "student" | "reviewer" | "admin";

export type DocumentStatus = "uploaded" | "parsing" | "embedding" | "indexed" | "failed";

export type GenerationKind =
  "question_bank" | "flashcards" | "study_plan" | "revision_sheet" | "test_help";

export type ReviewStatus = "pending" | "approved" | "rejected" | "needs_edit";

export type ChatKind = "mentor" | "concept";

export interface DbUser {
  id: string;
  email: string;
  created_at: string;
  last_sign_in_at: string | null;
}

export interface DbProfile {
  id: string; // == auth.users.id
  full_name: string;
  initials: string;
  avatar_url: string | null;
  created_at: string;
}

export interface DbUserRole {
  id: string;
  user_id: string;
  role: UserRole;
}

export interface DbWorkspace {
  id: string;
  owner_id: string;
  name: string;
  subject: string;
  description: string;
  accent: string | null;
  created_at: string;
  updated_at: string;
}

/** `workspace_with_owner` view row — workspaces joined with the owner profile
 * plus computed counts and the workspace's overall review status. */
export interface DbWorkspaceWithOwner extends DbWorkspace {
  owner_name: string;
  owner_email: string;
  document_count: number;
  generation_count: number;
  pending_review_count: number;
  review_status: ReviewStatus;
}

export interface DbDocument {
  id: string;
  workspace_id: string;
  uploaded_by: string;
  title: string;
  kind: string;
  size_bytes: number | null;
  pages: number | null;
  chunk_count: number;
  status: DocumentStatus;
  storage_path: string | null;
  notes: string | null;
  topics: string[];
  coverage: number | null;
  created_at: string;
}

export interface DbChunk {
  id: string;
  document_id: string;
  workspace_id: string;
  index: number;
  page: number | null;
  content: string;
  token_count: number | null;
}

export interface DbEmbedding {
  id: string;
  chunk_id: string;
  /** pgvector column */
  embedding: number[];
  model: string;
}

export interface DbGeneration {
  id: string;
  workspace_id: string;
  created_by: string;
  kind: GenerationKind;
  model: string;
  title: string;
  payload: unknown; // questions[] | flashcards[] | plan | sheet
  document_ids: string[];
  grounding_score: number | null;
  quality_score: number | null;
  review_status: ReviewStatus;
  created_at: string;
}

/** `generation_with_creator` view: generation rows + provenance columns. */
export interface DbGenerationWithCreator extends DbGeneration {
  creator_name: string | null;
  creator_email: string | null;
  workspace_name: string | null;
}

export interface DbGenerationVersion {
  id: string;
  generation_id: string;
  version: number;
  payload: unknown;
  edited_by: string | null;
  created_at: string;
}

export interface DbReview {
  id: string;
  generation_id: string;
  workspace_id: string;
  item_id: string;
  reviewer_id: string | null;
  status: ReviewStatus;
  comment: string | null;
  created_at: string;
}

export interface DbChat {
  id: string;
  workspace_id: string;
  user_id: string;
  kind: ChatKind;
  title: string;
  model: string;
  created_at: string;
}

export interface DbChatMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: unknown[] | null;
  created_at: string;
}

export interface DbNotification {
  id: string;
  user_id: string | null;
  workspace_id: string | null;
  roles: UserRole[];
  kind: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
}

export interface DbHistoryEntry {
  id: string;
  workspace_id: string;
  user_id: string;
  generation_id: string | null;
  kind: GenerationKind;
  title: string;
  model: string;
  review_status: ReviewStatus;
  created_at: string;
}

export interface DbAnalyticsSnapshot {
  workspace_id: string;
  captured_at: string;
  documents: number;
  generations: number;
  approvals: number;
  rejections: number;
  avg_grounding: number;
  avg_quality: number;
}

/** Per-user favorite flashcard, keyed by the card's stable front text. */
export interface FlashcardFavorite {
  id: string;
  user_id: string;
  generation_id: string | null;
  workspace_id: string | null;
  front: string;
  back: string | null;
  topic: string | null;
  format: string | null;
  source_chunk_id: string | null;
  created_at: string;
}

/** `pipeline_stats` view row — live chunks count plus config/measured telemetry (staff-gated). */
export interface DbPipelineStats {
  chunks_indexed: number;
  avg_retrieval_ms: number | null;
  top_k: number | null;
  embedding_model: string | null;
  validation_pass_rate: number | null;
  support_checked_pct: number | null;
  updated_at: string | null;
}

/** Convenience map mirroring the Supabase generated `Database` shape. */
export interface Database {
  public: {
    Tables: {
      profiles: { Row: DbProfile };
      user_roles: { Row: DbUserRole };
      workspaces: { Row: DbWorkspace };
      documents: { Row: DbDocument };
      chunks: { Row: DbChunk };
      embeddings: { Row: DbEmbedding };
      generations: { Row: DbGeneration };
      generation_versions: { Row: DbGenerationVersion };
      reviews: { Row: DbReview };
      chats: { Row: DbChat };
      chat_messages: { Row: DbChatMessage };
      notifications: { Row: DbNotification };
      history: { Row: DbHistoryEntry };
      analytics: { Row: DbAnalyticsSnapshot };
      flashcard_favorites: { Row: FlashcardFavorite };
      pipeline_telemetry: { Row: DbPipelineStats };
    };
    Views: {
      workspace_with_owner: { Row: DbWorkspaceWithOwner };
      pipeline_stats: { Row: DbPipelineStats };
    };
  };
}
