-- ============================================================================
-- 011_document_security.sql
--
-- Phase 7.3 — Document / Generation / Review security (RLS ownership model).
--
-- Requirement (Phase 7.3 security model — RLS ownership by workspace):
--   * Student   → full CRUD on the documents, generations and reviews that
--                 belong to workspaces they own. Read-only access to nothing
--                 owned by another student.
--   * Reviewer  → read-only access to documents/generations across ALL
--                 workspaces, plus write access to the review trail.
--   * Admin     → same read-everything model as reviewers (has_full_access).
--
-- 001 already creates owner-scoped policies (documents, generations, chunks,
-- embeddings, generation_versions) and a reviewer/admin policy on reviews.
-- This migration ADDS the missing read paths for staff (documents/generations/
-- chunks/embeddings/versions) and the owner read path for reviews so the Data
-- API enforces the full Phase 7.3 ownership model. Nothing existing is dropped
-- or rewritten.
--
-- Idempotency: every policy is created inside a pg_policies existence check
-- (same pattern as 009) and grants are unconditional — safe to re-run in the
-- SQL editor. Ordering: 011 > 010 > 009 > 008 > 001.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. GRANTs so the Data API can serve these tables to `authenticated`
--    (the coarse layer — RLS below is the actual gate). service_role is
--    granted for symmetry with the rest of the schema and bypasses RLS.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON public.documents TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chunks TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.embeddings TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.generations TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.generation_versions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reviews TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.history TO authenticated;

GRANT ALL ON public.documents TO service_role;
GRANT ALL ON public.chunks TO service_role;
GRANT ALL ON public.embeddings TO service_role;
GRANT ALL ON public.generations TO service_role;
GRANT ALL ON public.generation_versions TO service_role;
GRANT ALL ON public.reviews TO service_role;
GRANT ALL ON public.history TO service_role;

-- ---------------------------------------------------------------------------
-- 2. RLS policies
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  -- Documents ------------------------------------------------------------
  -- Staff (reviewer/admin, per has_full_access) read documents in every
  -- workspace. Owners already have full CRUD via 001's policy.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'documents'
      AND policyname = 'Workspace staff can read documents'
  ) THEN
    CREATE POLICY "Workspace staff can read documents"
      ON public.documents FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  -- Generations ----------------------------------------------------------
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'generations'
      AND policyname = 'Workspace staff can read generations'
  ) THEN
    CREATE POLICY "Workspace staff can read generations"
      ON public.generations FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  -- Reviews --------------------------------------------------------------
  -- Owners may read the review trail of their own workspace (review status,
  -- comments). Reviewers/admins already have FOR ALL via 001's policy.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reviews'
      AND policyname = 'Workspace owners can read reviews'
  ) THEN
    CREATE POLICY "Workspace owners can read reviews"
      ON public.reviews FOR SELECT TO authenticated
      USING (
        EXISTS (
          SELECT 1 FROM public.workspaces w
          WHERE w.id = reviews.workspace_id
            AND w.owner_id = (select auth.uid())
        )
      );
  END IF;

  -- Chunks (document children) ------------------------------------------
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'chunks'
      AND policyname = 'Workspace staff can read chunks'
  ) THEN
    CREATE POLICY "Workspace staff can read chunks"
      ON public.chunks FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  -- Embeddings (chunk children) -----------------------------------------
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'embeddings'
      AND policyname = 'Workspace staff can read embeddings'
  ) THEN
    CREATE POLICY "Workspace staff can read embeddings"
      ON public.embeddings FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  -- Generation versions (generation children) ---------------------------
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'generation_versions'
      AND policyname = 'Workspace staff can read versions'
  ) THEN
    CREATE POLICY "Workspace staff can read versions"
      ON public.generation_versions FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  -- History --------------------------------------------------------------
  -- Owners keep managing their own history (001); staff read all history so
  -- the review/audit surfaces can render workspace activity.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'history'
      AND policyname = 'Staff can read history'
  ) THEN
    CREATE POLICY "Staff can read history"
      ON public.history FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   -- Policies per table:
--   select tablename, policyname, cmd from pg_policies
--   where schemaname = 'public'
--     and tablename in ('documents','generations','reviews','chunks',
--                       'embeddings','generation_versions','history')
--   order by tablename, policyname;
--
--   -- As a student:      set request.jwt.claims = '{"sub":"<student_uid>","role":"authenticated"}'::jsonb;
--   --   select count(*) from documents;  -- only own workspace's rows
--   -- As a reviewer:     set request.jwt.claims = '{"sub":"<reviewer_uid>","role":"authenticated"}'::jsonb;
--   --   select count(*) from documents;  -- ALL documents
-- ---------------------------------------------------------------------------
