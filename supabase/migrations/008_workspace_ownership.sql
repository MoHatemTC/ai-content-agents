-- ============================================================================
-- 008_workspace_ownership.sql
--
-- Phase 7.1 — Workspace ownership.
--
-- Exposes the workspace list the frontend renders (the `Workspace` domain model
-- in src/types/domain.ts) as a single denormalised read model so
-- src/api/workspace.api.ts can load workspaces together with the owner identity
-- and the review summary in one query.
--
-- Scope is deliberately Phase 7.1 ONLY:
--   * `workspace_with_owner` view  (owner-info joins + computed review fields)
--   * supporting indexes
--   * GRANTs
--
-- Deliberately NOT in this migration (land in Phase 7.2): RLS, policies,
-- the `app_role` enum and the `has_role()` helper, visibility filtering.
--
-- The base schema (workspaces, documents, generations, profiles and
-- auth.users) is created outside these migration files — see
-- docs/DATABASE_SCHEMA.md and src/types/database.types.ts.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- workspace_with_owner view
--
-- Joins workspaces -> profiles (owner full_name) and auth.users (owner email),
-- then adds per-workspace aggregates over documents and generations:
--   * document_count         total documents in the workspace
--   * generation_count       total generations in the workspace
--   * pending_review_count   generations still awaiting review
--   * review_status          review status of the workspace's most recent
--                            generation ('pending' when there are none)
--
-- A plain (security-definer) view runs with the view owner's privileges, so
-- the GRANTs below are the only access `authenticated` needs — it never reads
-- auth.users or the base tables directly.
--
-- CREATE OR REPLACE keeps the object idempotent and lets Phase 7.2 add its
-- visibility WHERE clause to the same view without recreating dependent
-- objects.
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
LEFT JOIN auth.users   au ON au.id = w.owner_id;

COMMENT ON VIEW public.workspace_with_owner IS
    'Workspaces joined with owner identity and review summary (Phase 7.1).';
COMMENT ON COLUMN public.workspace_with_owner.owner_name IS
    'Owner display name from profiles.full_name.';
COMMENT ON COLUMN public.workspace_with_owner.owner_email IS
    'Owner email from auth.users (not directly readable by anon/authenticated).';
COMMENT ON COLUMN public.workspace_with_owner.document_count IS
    'Total documents in the workspace.';
COMMENT ON COLUMN public.workspace_with_owner.generation_count IS
    'Total generations in the workspace.';
COMMENT ON COLUMN public.workspace_with_owner.pending_review_count IS
    'Generations with review_status = ''pending''.';
COMMENT ON COLUMN public.workspace_with_owner.review_status IS
    'Review status of the workspace''s most recent generation; ''pending'' when the workspace has no generations.';

-- ---------------------------------------------------------------------------
-- Supporting indexes
--
-- Feed the view''s per-workspace aggregates. IF NOT EXISTS keeps the migration
-- idempotent against a base schema that may already carry these indexes.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_documents_workspace_id
    ON public.documents (workspace_id);

CREATE INDEX IF NOT EXISTS idx_generations_workspace_id
    ON public.generations (workspace_id);

CREATE INDEX IF NOT EXISTS idx_generations_workspace_review_status
    ON public.generations (workspace_id, review_status);

CREATE INDEX IF NOT EXISTS idx_generations_workspace_created_at
    ON public.generations (workspace_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- GRANTs
--
-- SELECT on the view is all `authenticated` gets — the view (not the base
-- tables) is the read path for the workspace list. service_role bypasses RLS
-- but is granted for symmetry with the rest of the schema.
-- ---------------------------------------------------------------------------
GRANT SELECT ON public.workspace_with_owner TO authenticated;
GRANT SELECT ON public.workspace_with_owner TO service_role;
