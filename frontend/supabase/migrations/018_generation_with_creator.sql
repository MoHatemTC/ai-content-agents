-- ============================================================================
-- 018_generation_with_creator.sql
--
-- Phase 8.2 — Human review provenance.
--
-- The reviewer page shows, per queued item, which account created it and from
-- which workspace it came. Generation rows carry `created_by` + `workspace_id`
-- but:
--   * `profiles` RLS only lets a user read their OWN profile, so a reviewer
--     cannot resolve a creator's display name/email directly;
--   * workspace names need the join used by `workspace_with_owner`.
--
-- This adds `generation_with_creator`, the same shape PostgREST already treats
-- as a security-definer view (see `workspace_with_owner` in 009/010): the
-- predicate keeps the app's existing visibility model — staff
-- (`has_full_access`) see every generation with provenance, owners see their
-- own — while the join to `profiles` / `auth.users` / `workspaces` runs as the
-- view owner so names resolve for staff.
--
-- Idempotent (CREATE OR REPLACE VIEW + re-issued GRANTs). Safe to re-run.
-- Ordering: 018 > 016 > 013 > 011 > 009 > 008 > 001.
-- ============================================================================

CREATE OR REPLACE VIEW public.generation_with_creator AS
SELECT
    g.id,
    g.workspace_id,
    g.created_by,
    g.kind,
    g.model,
    g.title,
    g.payload,
    g.document_ids,
    g.grounding_score,
    g.quality_score,
    g.review_status,
    g.created_at,
    p.full_name    AS creator_name,
    au.email       AS creator_email,
    w.name         AS workspace_name
FROM public.generations g
LEFT JOIN public.profiles p  ON p.id = g.created_by
LEFT JOIN auth.users   au   ON au.id = g.created_by
LEFT JOIN public.workspaces w ON w.id = g.workspace_id
WHERE public.has_full_access((select auth.uid()))
   OR g.workspace_id IN (
        SELECT w2.id FROM public.workspaces w2 WHERE w2.owner_id = (select auth.uid())
      );

COMMENT ON VIEW public.generation_with_creator IS
    'Generations joined with creator identity and workspace name, filtered to the caller''s visibility (staff: all; owner: own).';

GRANT SELECT ON public.generation_with_creator TO authenticated;
GRANT SELECT ON public.generation_with_creator TO service_role;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   -- As a reviewer/admin: every generation with creator + workspace names.
--   select title, creator_name, creator_email, workspace_name
--   from public.generation_with_creator order by created_at desc limit 10;
--
--   -- As a student: only generations from workspaces you own.
-- ---------------------------------------------------------------------------
