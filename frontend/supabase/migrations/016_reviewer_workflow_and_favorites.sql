-- ============================================================================
-- 016_reviewer_workflow_and_favorites.sql
--
-- Phase 8 — Reviewer workflow (staff writes) + Supabase flashcard favorites.
--
-- Generations:
--   * Staff (reviewer/admin) may UPDATE the review status of any generation so
--     the review queue can advance rows from 'pending' -> 'approved' etc. This
--     complements 011's read-only staff access. (Owners keep full CRUD via 001.)
--   * A new SECURITY DEFINER trigger notifies the reviewer/admin roles whenever
--     a reviewable generation is created, so the staff notification feed shows
--     "New output awaiting review" with the workspace name. The owner is already
--     notified by 013's `notify_generation_created`.
--
-- Favorites:
--   * `flashcard_favorites` — per-user favorites for generated flashcards,
--     keyed by the card's front text (stable across regenerations). RLS limits
--     every row to its owner.
--
-- Idempotency: policies use a pg_policies existence check, triggers are
-- re-created via DROP IF EXISTS + CREATE, functions use CREATE OR REPLACE,
-- tables use IF NOT EXISTS. Safe to re-run in the SQL editor.
-- Ordering: 016 > 013 > 011 > 009 > 008 > 001.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Staff may advance a generation's review status.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'generations'
      AND policyname = 'Workspace staff can update review status'
  ) THEN
    CREATE POLICY "Workspace staff can update review status"
      ON public.generations FOR UPDATE TO authenticated
      USING (public.has_full_access((select auth.uid())))
      WITH CHECK (public.has_full_access((select auth.uid())));
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Staff pending-review notifications.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.notify_staff_pending_review()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  wname text;
BEGIN
  IF NEW.kind IN ('question_bank', 'flashcards', 'test_help', 'study_plan', 'revision_sheet') THEN
    SELECT w.name INTO wname FROM public.workspaces w WHERE w.id = NEW.workspace_id;
    PERFORM public.create_notification(
      NULL,
      NEW.workspace_id,
      ARRAY['reviewer', 'admin']::public.app_role[],
      'review',
      'New output awaiting review',
      format('%s · %s', COALESCE(wname, 'A workspace'), NEW.title)
    );
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_staff_pending_review_notify ON public.generations;
CREATE TRIGGER trg_staff_pending_review_notify
AFTER INSERT ON public.generations
FOR EACH ROW
EXECUTE FUNCTION public.notify_staff_pending_review();

-- ---------------------------------------------------------------------------
-- 3. Flashcard favorites.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.flashcard_favorites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  generation_id uuid REFERENCES public.generations(id) ON DELETE SET NULL,
  front text NOT NULL,
  back text,
  topic text,
  format text,
  source_chunk_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, front)
);

ALTER TABLE public.flashcard_favorites ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'flashcard_favorites'
      AND policyname = 'Users manage their flashcard favorites'
  ) THEN
    CREATE POLICY "Users manage their flashcard favorites"
      ON public.flashcard_favorites FOR ALL TO authenticated
      USING (user_id = auth.uid())
      WITH CHECK (user_id = auth.uid());
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_flashcard_favorites_user
  ON public.flashcard_favorites (user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.flashcard_favorites TO authenticated;
GRANT ALL ON public.flashcard_favorites TO service_role;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   select policyname, cmd from pg_policies
--   where tablename in ('generations', 'flashcard_favorites');
--
--   -- Insert a generation as a student, then (as reviewer):
--   select title, body from public.notifications
--   where 'reviewer' = ANY(roles) order by created_at desc;
-- ---------------------------------------------------------------------------
