-- ============================================================================
-- 019_pipeline_telemetry.sql
--
-- Phase 8.3 — Live RAG pipeline telemetry.
--
-- The RAG Pipeline page (and admin surfaces) show six headline numbers:
--   * Chunks indexed          → computed LIVE from public.chunks
--   * Avg. retrieval latency  → measured value, stored here (updated by the
--                               backend / admins as measurements come in)
--   * Top-k                   → config value (hybrid retrieval k)
--   * Embedding model         → config value
--   * Validation pass rate    → measured value (schema validation)
--   * Support checked         → measured value (% outputs checked)
--
-- `pipeline_telemetry` is a single-row (id = 1) table that holds the
-- config/measured values. `pipeline_stats` is a security-definer view that
-- joins them with the live chunks count and gates reads to staff
-- (has_full_access), exactly like `workspace_with_owner`.
--
-- Nothing in this migration touches localStorage or reads client state; the
-- frontend reads the view through the Data API, so every number reflects the
-- live database.
--
-- Idempotency: table uses IF NOT EXISTS, the seed uses ON CONFLICT, policies
-- use a pg_policies existence check, and the view uses CREATE OR REPLACE —
-- safe to re-run in the Supabase SQL editor.
-- Ordering: 019 > 016 > 011 > 009 > 008 > 001.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Telemetry table (single row, id = 1).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pipeline_telemetry (
  id                    integer PRIMARY KEY CHECK (id = 1),
  avg_retrieval_ms      numeric,
  top_k                 integer,
  embedding_model       text,
  validation_pass_rate  numeric,          -- % of outputs passing schema validation
  support_checked_pct   numeric,          -- % of outputs whose answers are verified
  updated_at            timestamptz NOT NULL DEFAULT now()
);

-- Seed with the current platform values so the page is never empty. The seed
-- row is what the backend will UPDATE as real measurements arrive.
INSERT INTO public.pipeline_telemetry
  (id, avg_retrieval_ms, top_k, embedding_model, validation_pass_rate, support_checked_pct)
VALUES
  (1, 184, 8, 'gemini-embedding-001', 97.2, 100)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. RLS — only staff (reviewer/admin) may read or update telemetry.
-- ---------------------------------------------------------------------------
ALTER TABLE public.pipeline_telemetry ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'pipeline_telemetry'
      AND policyname = 'Staff can read pipeline telemetry'
  ) THEN
    CREATE POLICY "Staff can read pipeline telemetry"
      ON public.pipeline_telemetry FOR SELECT TO authenticated
      USING (public.has_full_access((select auth.uid())));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'pipeline_telemetry'
      AND policyname = 'Staff can update pipeline telemetry'
  ) THEN
    CREATE POLICY "Staff can update pipeline telemetry"
      ON public.pipeline_telemetry FOR UPDATE TO authenticated
      USING (public.has_full_access((select auth.uid())))
      WITH CHECK (public.has_full_access((select auth.uid())));
  END IF;
END $$;

GRANT SELECT, UPDATE ON public.pipeline_telemetry TO authenticated;
GRANT ALL ON public.pipeline_telemetry TO service_role;

-- ---------------------------------------------------------------------------
-- 3. pipeline_stats view — live chunks count + telemetry, staff-gated.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.pipeline_stats AS
SELECT
  (SELECT count(*) FROM public.chunks)::bigint                AS chunks_indexed,
  t.avg_retrieval_ms,
  t.top_k,
  t.embedding_model,
  t.validation_pass_rate,
  t.support_checked_pct,
  t.updated_at
FROM public.pipeline_telemetry t
WHERE t.id = 1
  AND public.has_full_access((select auth.uid()));

COMMENT ON VIEW public.pipeline_stats IS
  'Live RAG pipeline telemetry: chunks indexed (computed) plus config/measured values, visible to staff only (Phase 8.3).';

GRANT SELECT ON public.pipeline_stats TO authenticated;
GRANT SELECT ON public.pipeline_stats TO service_role;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   -- As the admin/reviewer account:
--   select * from public.pipeline_stats;
--   -- chunks_indexed reflects the live count of public.chunks.
--
--   -- As the student account: the same query returns no rows (staff-gated).
--
--   -- Update measurements as they arrive (backend or admin):
--   update public.pipeline_telemetry
--   set avg_retrieval_ms = 152, validation_pass_rate = 97.8, updated_at = now()
--   where id = 1;
-- ---------------------------------------------------------------------------
