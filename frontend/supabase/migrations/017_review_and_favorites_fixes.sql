-- ============================================================================
-- 017_review_and_favorites_fixes.sql
--
-- Phase 8.1 — Two fixes on top of 016:
--
-- 1. Reviews upsert key.
--    `ReviewService.decideItem` upserts reviews with
--    `onConflict: 'generation_id,item_id'`, but 001 created no unique
--    constraint on those columns. The upsert therefore failed with "no unique
--    or exclusion constraint matching the ON CONFLICT specification", which
--    surfaced as "Could not persist the decision" when a reviewer approved or
--    rejected an item. This adds the missing unique index (and constraint).
--
-- 2. Per-workspace favorites.
--    `flashcard_favorites` had no workspace link, so favorites leaked across
--    workspaces. This adds a nullable `workspace_id` (NULL keeps legacy rows
--    visible; new favorites always carry one), an index for the owner+workspace
--    query, and a foreign key so deleting a workspace removes its favorites.
--
-- Idempotency: ALTER TABLE ... ADD COLUMN IF NOT EXISTS, unique index guarded
-- by IF NOT EXISTS, constraint added only when absent. Safe to re-run in the
-- Supabase SQL editor. Ordering: 017 > 016 > 013 > 011 > 009 > 008 > 001.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. reviews: unique key for the app's upsert.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS reviews_generation_item_key
  ON public.reviews (generation_id, item_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'reviews_generation_item_key'
  ) THEN
    ALTER TABLE public.reviews
      ADD CONSTRAINT reviews_generation_item_key
      UNIQUE USING INDEX reviews_generation_item_key;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. flashcard_favorites: scope favorites to the workspace they came from.
-- ---------------------------------------------------------------------------
ALTER TABLE public.flashcard_favorites
  ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES public.workspaces(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_flashcard_favorites_workspace
  ON public.flashcard_favorites (user_id, workspace_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.flashcard_favorites TO authenticated;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   select conname, conrelid::regclass from pg_constraint
--   where conname = 'reviews_generation_item_key';
--
--   select column_name from information_schema.columns
--   where table_name = 'flashcard_favorites' and column_name = 'workspace_id';
-- ---------------------------------------------------------------------------
