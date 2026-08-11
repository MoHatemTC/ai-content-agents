-- ============================================================================
-- 010_workspace_visibility_hard_fix.sql
--
-- Phase 7.2 root-cause fix for workspace visibility.
--
-- Problem: 009's detect-and-create guards skipped replacing the OLD
-- `public.has_role(uuid, app_role)` that 001_initial_schema.sql already
-- created (create or replace). `has_full_access` therefore stays bound to the
-- OLD function and the live `user_roles` rows it reads; in the live DB those
-- rows resolve the "student" account as staff, so the view's
-- `WHERE has_full_access(...)` passes for every row and the student sees every
-- workspace.
--
-- Fix: CREATE OR REPLACE is non-destructive — it swaps the function bodies in
-- place, keeps the same OIDs, and does NOT break the view or RLS policies that
-- reference these functions. No DROP, no tables/enums/triggers touched.
-- 010 is idempotent and safe to re-run in the Supabase SQL editor.
--
-- Ordering: 010 > 009 > 008. Requires the objects from 001 and 009 to exist.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Force the intended role helpers to be the live ones.
--
-- CREATE OR REPLACE replaces the existing 001 definition in place (same OID),
-- so `workspace_with_owner` and the `workspace_*` policies keep their valid
-- references — no dependency breakage, no DROP ... CASCADE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.has_role(user_id uuid, required public.app_role)
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

CREATE OR REPLACE FUNCTION public.has_full_access(uid uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $fn$
  SELECT uid IS NULL
      OR public.has_role(uid, 'admin')
      OR public.has_role(uid, 'reviewer');
$fn$;

GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;
GRANT EXECUTE ON FUNCTION public.has_full_access(uuid) TO authenticated;

-- ---------------------------------------------------------------------------
-- 2. Re-assert the gate (same shape as 009; CREATE OR REPLACE is idempotent).
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
-- 3. GRANTs (re-issued; idempotent)
-- ---------------------------------------------------------------------------
GRANT SELECT ON public.workspace_with_owner TO authenticated;
GRANT SELECT ON public.workspace_with_owner TO service_role;

-- ---------------------------------------------------------------------------
-- 4. DATA CLEANUP (the actual staff grant lives in the data, not the code).
--
-- 010 fixes the function binding; if the "student" account still holds
-- 'reviewer'/'admin' rows in public.user_roles, remove them so the account
-- resolves as a pure student. Run this ONCE after 010, replacing
-- <student_auth_uid> with the student's auth.users id.
-- ---------------------------------------------------------------------------
-- DELETE FROM public.user_roles
-- WHERE user_id = '<student_auth_uid>' AND role IN ('reviewer', 'admin');
--
-- Confirm: select * from public.user_roles where user_id = '<student_auth_uid>';
-- should show only the ('student') row.
-- Then sign in as the student and run:
--   select id, owner_id, name from public.workspace_with_owner;
-- non-owned workspaces must no longer appear.
