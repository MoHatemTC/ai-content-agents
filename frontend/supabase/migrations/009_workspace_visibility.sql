-- ============================================================================
-- 009_workspace_visibility.sql
--
-- Phase 7.2 — RLS workspace visibility.
--
-- Makes workspace visibility a server-side decision:
--
--   * Student  → sees ONLY workspaces they own (owner_id = auth.uid()).
--   * Reviewer → sees their own plus every student workspace.
--   * Admin    → sees everything.
--
-- How it works:
--   * `workspace_with_owner` is a security-definer view (PostgREST lints it,
--     but the view's own WHERE clause now gates every row with the same
--     visibility predicate, so RLS-bypass by the view is not a leak). The
--     view keeps reading profiles/auth.users as its owner, so NO new grants
--     on base tables or auth.users are needed.
--   * The same predicate is ALSO expressed as RLS policies on `workspaces`
--     (defense in depth for direct table access, matching the workspace
--     visibility model).
--   * `has_role()` / `has_full_access()` are SECURITY DEFINER helpers so
--     policies and the view can read `user_roles` without RLS recursion.
--
-- Deliberately NOT in this migration (land in Phase 7.3): RLS on child
-- tables (documents, generations, reviews), storage buckets, realtime.
--
-- Idempotency: every object is created only if missing — the app_role enum
-- and functions are guarded by pg_type/to_regprocedure checks, the
-- user_roles table and indexes use IF NOT EXISTS, policies are created via a
-- pg_policies existence check, and the view uses CREATE OR REPLACE. Nothing
-- is DROPped and no existing definition is silently overwritten, so 009 is
-- safe to re-run in the Supabase SQL editor AND to keep as a single entry in
-- the migration history. Ordering 009 > 008.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. app_role enum + user_roles table (guarded — the base schema lives
--    outside the migration chain; these are Phase 7.2's only hard prereqs).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'app_role' AND n.nspname = 'public'
  ) THEN
    CREATE TYPE public.app_role AS ENUM ('student', 'reviewer', 'admin');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.user_roles (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  role    public.app_role NOT NULL,
  UNIQUE (user_id, role)
);

-- ---------------------------------------------------------------------------
-- 2. Role helpers
--
-- Functions are created ONLY if missing (detect-and-create via
-- to_regprocedure), never dropped or blindly replaced. In a migration
-- history each migration runs once, but 009 also needs to be safe to re-run
-- in the SQL editor, so nothing here should delete or silently overwrite an
-- existing definition.
-- ---------------------------------------------------------------------------

-- SECURITY DEFINER so policies
-- and the security-definer view can read user_roles without RLS recursion.
DO $$
BEGIN
  IF to_regprocedure('public.has_role(uuid, public.app_role)') IS NULL THEN
    CREATE FUNCTION public.has_role(user_id uuid, required public.app_role)
    RETURNS boolean
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = public
    AS $fn$
      SELECT EXISTS (
        SELECT 1 FROM public.user_roles ur
        WHERE ur.user_id = has_role.user_id
          AND ur.role   = has_role.required
      );
    $fn$;
  END IF;
END $$;

-- True for admins and reviewers. A NULL uid (service_role / SQL editor / cron
-- requests have no JWT) is treated as full access so trusted contexts keep
-- reading; the anon role never reaches this function (no GRANT on the view).
DO $$
BEGIN
  IF to_regprocedure('public.has_full_access(uuid)') IS NULL THEN
    CREATE FUNCTION public.has_full_access(uid uuid)
    RETURNS boolean
    LANGUAGE sql
    STABLE
    AS $fn$
      SELECT uid IS NULL
          OR public.has_role(uid, 'admin')
          OR public.has_role(uid, 'reviewer');
    $fn$;
  END IF;
END $$;

GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;
GRANT EXECUTE ON FUNCTION public.has_full_access(uuid) TO authenticated;

-- ---------------------------------------------------------------------------
-- 3. RLS on workspaces (defense in depth + documented §5 behaviour)
-- ---------------------------------------------------------------------------
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'workspaces'
      AND policyname = 'workspace_owner_access'
  ) THEN
    CREATE POLICY "workspace_owner_access"
      ON public.workspaces FOR ALL TO authenticated
      USING ((select auth.uid()) = owner_id)
      WITH CHECK ((select auth.uid()) = owner_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'workspaces'
      AND policyname = 'workspace_staff_read'
  ) THEN
    CREATE POLICY "workspace_staff_read"
      ON public.workspaces FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'workspaces'
      AND policyname = 'workspace_staff_write'
  ) THEN
    CREATE POLICY "workspace_staff_write"
      ON public.workspaces FOR UPDATE TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Indexes for the policy / view predicates
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id
  ON public.workspaces (owner_id);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id
  ON public.user_roles (user_id);

-- ---------------------------------------------------------------------------
-- 5. Re-create workspace_with_owner with the visibility predicate.
--
-- The view stays security-definer so the owner-info joins keep working with
-- only the view-level GRANT — but every returned row is gated by the same
-- predicate the RLS policies use, so students never see other students'
-- workspaces through the app's read path.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.workspace_with_owner AS
SELECT
    w.id,
    w.owner_id,
    w.name,
    w.subject,
    w.description,
    w.accent,
    w.created_at,
    w.updated_at,
    p.full_name AS owner_name,
    au.email    AS owner_email,
    (SELECT count(*) FROM public.documents d WHERE d.workspace_id = w.id)
        AS document_count,
    (SELECT count(*) FROM public.generations g WHERE g.workspace_id = w.id)
        AS generation_count,
    (SELECT count(*) FROM public.generations g
        WHERE g.workspace_id = w.id AND g.review_status = 'pending')
        AS pending_review_count,
    COALESCE((
        SELECT g.review_status
        FROM public.generations g
        WHERE g.workspace_id = w.id
        ORDER BY g.created_at DESC, g.id DESC
        LIMIT 1
    ), 'pending') AS review_status
FROM public.workspaces w
LEFT JOIN public.profiles p ON p.id = w.owner_id
LEFT JOIN auth.users   au ON au.id = w.owner_id
WHERE public.has_full_access((select auth.uid()))
   OR w.owner_id = (select auth.uid());

COMMENT ON VIEW public.workspace_with_owner IS
    'Workspaces joined with owner identity and review summary, filtered to the caller''s visibility (Phase 7.1 + 7.2).';

-- ---------------------------------------------------------------------------
-- 6. GRANTs (re-issued; idempotent)
-- ---------------------------------------------------------------------------
GRANT SELECT ON public.workspace_with_owner TO authenticated;
GRANT SELECT ON public.workspace_with_owner TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.workspaces TO authenticated;
GRANT ALL ON public.workspaces TO service_role;
