-- ============================================================================
-- 012_storage_security.sql
--
-- Phase 7.3 — Secure Supabase Storage.
--
-- The `documents` bucket holds uploaded lecture files at
--   <workspaceId>/<documentId>/<fileName>
-- so the workspace id is always the first path segment.
--
-- 002 created three very lax storage policies (ANY authenticated user could
-- upload/read/delete ANY file in the bucket). This migration:
--   1. ensures the private `documents` bucket exists (100 MB limit, non-public),
--   2. REPLACES the lax policies with ownership-aware ones:
--        * upload/update/delete  → workspace owner only
--        * download (select)     → workspace owner OR staff (has_full_access)
--   3. adds a security-definer signed-URL helper for the backend so files are
--      served with expiring signed URLs, never through public access.
--
-- Idempotency: bucket upsert + DROP POLICY IF EXISTS + pg_policies guards for
-- the new policies + CREATE OR REPLACE on helpers. Safe to re-run.
-- Ordering: 012 > 011 > 010 > 002.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Private `documents` bucket (create if missing, keep it private, 100 MB).
-- ---------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('documents', 'documents', false, 104857600, NULL)
ON CONFLICT (id) DO UPDATE
  SET public = false,
      file_size_limit = 104857600;

-- ---------------------------------------------------------------------------
-- 2. Path helper: extract the workspace uuid from a storage path, or NULL when
--    the first segment is not a valid uuid (prevents ::uuid errors in policies
--    for malformed paths).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.storage_workspace_id(p_path text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT CASE
    WHEN (storage.foldername(p_path))[1] ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (storage.foldername(p_path))[1]::uuid
    ELSE NULL
  END;
$$;

GRANT EXECUTE ON FUNCTION public.storage_workspace_id(text) TO authenticated;

-- ---------------------------------------------------------------------------
-- 3. Drop the lax 002 policies (idempotent) and re-create ownership-aware ones.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can upload their own files" ON storage.objects;
DROP POLICY IF EXISTS "Users can read their own files" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete their own files" ON storage.objects;

DO $$
BEGIN
  -- Owner may upload (INSERT) into their own workspace's folder.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'Documents: workspace owner can upload'
  ) THEN
    CREATE POLICY "Documents: workspace owner can upload"
      ON storage.objects FOR INSERT TO authenticated
      WITH CHECK (
        bucket_id = 'documents'
        AND public.storage_workspace_id(name) IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM public.workspaces w
          WHERE w.id = public.storage_workspace_id(name)
            AND w.owner_id = (select auth.uid())
        )
      );
  END IF;

  -- Owner or staff (reviewer/admin) may download (SELECT).
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'Documents: workspace owner or staff can download'
  ) THEN
    CREATE POLICY "Documents: workspace owner or staff can download"
      ON storage.objects FOR SELECT TO authenticated
      USING (
        bucket_id = 'documents'
        AND public.storage_workspace_id(name) IS NOT NULL
        AND (
          EXISTS (
            SELECT 1 FROM public.workspaces w
            WHERE w.id = public.storage_workspace_id(name)
              AND w.owner_id = (select auth.uid())
          )
          OR public.has_full_access((select auth.uid()))
        )
      );
  END IF;

  -- Owner may update (overwrite) their own files.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'Documents: workspace owner can update'
  ) THEN
    CREATE POLICY "Documents: workspace owner can update"
      ON storage.objects FOR UPDATE TO authenticated
      USING (
        bucket_id = 'documents'
        AND public.storage_workspace_id(name) IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM public.workspaces w
          WHERE w.id = public.storage_workspace_id(name)
            AND w.owner_id = (select auth.uid())
        )
      )
      WITH CHECK (
        bucket_id = 'documents'
        AND public.storage_workspace_id(name) IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM public.workspaces w
          WHERE w.id = public.storage_workspace_id(name)
            AND w.owner_id = (select auth.uid())
        )
      );
  END IF;

  -- Owner may delete their own files.
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'Documents: workspace owner can delete'
  ) THEN
    CREATE POLICY "Documents: workspace owner can delete"
      ON storage.objects FOR DELETE TO authenticated
      USING (
        bucket_id = 'documents'
        AND public.storage_workspace_id(name) IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM public.workspaces w
          WHERE w.id = public.storage_workspace_id(name)
            AND w.owner_id = (select auth.uid())
        )
      );
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Signed-URL helper (backend storage support):
--
-- Returns a short-lived signed URL for a document path, but only when the
-- caller is the workspace owner or staff. The bucket itself is private, so the
-- signed URL is the ONLY way a browser/backend can fetch file bytes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_document_signed_url(
  p_path text,
  p_expires int DEFAULT 3600
)
RETURNS text
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = storage, public
AS $$
DECLARE
  v_workspace uuid;
  v_signed    text;
BEGIN
  v_workspace := public.storage_workspace_id(p_path);
  IF v_workspace IS NULL THEN
    RAISE EXCEPTION 'invalid storage path';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.workspaces w
    WHERE w.id = v_workspace
      AND (w.owner_id = auth.uid() OR public.has_full_access(auth.uid()))
  ) THEN
    RAISE EXCEPTION 'access denied to document storage';
  END IF;

  SELECT (storage.create_signed_url('documents', p_path, p_expires)).signed_url
    INTO v_signed;

  RETURN v_signed;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_document_signed_url(text, int) TO authenticated;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   select id, name, public from storage.buckets where id = 'documents';
--   select policyname, cmd from pg_policies
--   where schemaname = 'storage' and tablename = 'objects';
--
--   -- As a workspace owner:
--   --   select public.get_document_signed_url('<workspaceId>/<docId>/a.pdf', 300);
--   -- returns a https://...storage.../documents/... signed URL.
--   -- As another student, the same call raises 'access denied to document storage'.
-- ---------------------------------------------------------------------------
