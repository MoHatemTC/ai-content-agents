-- ============================================================================
-- 014_performance_indexes.sql
--
-- Phase 7.5 — Database optimization.
--
-- 008 already added the composite indexes that feed the `workspace_with_owner`
-- aggregates (documents/generations by workspace_id, review status and
-- created_at). This migration adds the remaining feed/queue/workload indexes:
--
--   * reviews(workspace_id, created_at DESC)   — review queues + audit trail
--   * notifications(user_id, read)             — unread badge counts
--   * generations(created_by)                  — "my generations" lists
--   * documents(workspace_id, created_at DESC) — document explorer feeds
--   * history(workspace_id, created_at DESC)   — history feeds
--   * chats(workspace_id, created_at DESC)     — conversation lists
--
-- All are CREATE INDEX IF NOT EXISTS → fully idempotent, no DROP, safe to
-- re-run. Ordering: 014 > 013.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_reviews_workspace_created
  ON public.reviews (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_user_read
  ON public.notifications (user_id, read);

CREATE INDEX IF NOT EXISTS idx_generations_created_by
  ON public.generations (created_by);

CREATE INDEX IF NOT EXISTS idx_documents_workspace_created
  ON public.documents (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_history_workspace_created
  ON public.history (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chats_workspace_created
  ON public.chats (workspace_id, created_at DESC);
