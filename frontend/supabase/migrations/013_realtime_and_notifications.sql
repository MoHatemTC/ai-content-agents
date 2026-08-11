-- ============================================================================
-- 013_realtime_and_notifications.sql
--
-- Phase 7.4 — Realtime + lightweight notification model (backend support).
--
-- Realtime:
--   * Adds workspaces, documents, generations, reviews and notifications to
--     the `supabase_realtime` publication so Postgres Changes can be consumed
--     by the frontend (RLS still filters every delivered change to what the
--     subscribed user may see).
--   * The frontend subscribes to `workspaces` and invalidates ONLY the
--     `["workspace-bootstrap"]` React Query cache (see WorkspaceContext.tsx).
--
-- Notifications:
--   * A lightweight model built on the existing `notifications` table.
--   * SECURITY DEFINER triggers write notifications when:
--       - a generation is created        ("Generation completed")
--       - a review row is inserted/updated ("Review finished")
--       - a document is uploaded          ("Document uploaded")
--     Notifications target the workspace OWNER (user_id = owner id), so they
--     are readable through the existing "Users read their own notifications"
--     policy.
--   * Adds a role-targeted read policy so reviewers/admins can receive
--     broadcast notifications via the `roles` array. No notification UI is
--     added — this is backend/service support only.
--
-- Idempotency: publication membership is guarded by pg_publication_tables;
-- triggers are re-created via DROP IF EXISTS + CREATE; functions use
-- CREATE OR REPLACE; the policy uses a pg_policies guard.
-- Ordering: 013 > 012 > 011 > 010.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Realtime publication membership (idempotent).
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['workspaces', 'documents', 'generations', 'reviews', 'notifications']
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = t
    ) THEN
      EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
    END IF;
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Notification helper + triggers.
-- ---------------------------------------------------------------------------

-- Single write point for app notifications. SECURITY DEFINER so triggers can
-- insert on behalf of the target user regardless of the invoking role.
CREATE OR REPLACE FUNCTION public.create_notification(
  p_user_id uuid,
  p_workspace_id uuid,
  p_roles public.app_role[],
  p_kind text,
  p_title text,
  p_body text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.notifications (user_id, workspace_id, roles, kind, title, body)
  VALUES (p_user_id, p_workspace_id, p_roles, p_kind, p_title, p_body);
END;
$$;

GRANT EXECUTE ON FUNCTION public.create_notification(uuid, uuid, public.app_role[], text, text, text)
  TO authenticated;

-- Generation created → notify the workspace owner.
CREATE OR REPLACE FUNCTION public.notify_generation_created()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM public.create_notification(
    (SELECT w.owner_id FROM public.workspaces w WHERE w.id = NEW.workspace_id),
    NEW.workspace_id,
    ARRAY['student']::public.app_role[],
    'done',
    'Generation completed',
    format('%s is ready to review', NEW.title)
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_generation_created_notify ON public.generations;
CREATE TRIGGER trg_generation_created_notify
AFTER INSERT ON public.generations
FOR EACH ROW
EXECUTE FUNCTION public.notify_generation_created();

-- Review row inserted/updated → notify the workspace owner.
CREATE OR REPLACE FUNCTION public.notify_review_finished()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM public.create_notification(
    (SELECT w.owner_id FROM public.workspaces w WHERE w.id = NEW.workspace_id),
    NEW.workspace_id,
    ARRAY['student']::public.app_role[],
    'review',
    'Review finished',
    format('A review on this workspace is now %s', NEW.status)
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_review_finished_notify ON public.reviews;
CREATE TRIGGER trg_review_finished_notify
AFTER INSERT OR UPDATE ON public.reviews
FOR EACH ROW
EXECUTE FUNCTION public.notify_review_finished();

-- Document uploaded → notify the workspace owner.
CREATE OR REPLACE FUNCTION public.notify_document_uploaded()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM public.create_notification(
    (SELECT w.owner_id FROM public.workspaces w WHERE w.id = NEW.workspace_id),
    NEW.workspace_id,
    ARRAY['student']::public.app_role[],
    'validation',
    'Document uploaded',
    format('%s is queued for parsing', NEW.title)
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_document_uploaded_notify ON public.documents;
CREATE TRIGGER trg_document_uploaded_notify
AFTER INSERT ON public.documents
FOR EACH ROW
EXECUTE FUNCTION public.notify_document_uploaded();

-- ---------------------------------------------------------------------------
-- 3. Role-targeted notification read policy (for broadcast notifications).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'notifications'
      AND policyname = 'Staff can read role notifications'
  ) THEN
    CREATE POLICY "Staff can read role notifications"
      ON public.notifications FOR SELECT TO authenticated
      USING (
        public.has_full_access((select auth.uid()))
        AND ('reviewer' = ANY(roles) OR 'admin' = ANY(roles))
      );
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.notifications TO authenticated;
GRANT ALL ON public.notifications TO service_role;

-- ---------------------------------------------------------------------------
-- Verification (run in the SQL editor after applying):
--
--   select schemaname, pubname, tablename from pg_publication_tables
--   where pubname = 'supabase_realtime';
--
--   -- Insert a generation as service_role, then:
--   select title, body, read from public.notifications order by created_at desc;
--   -- the workspace owner sees one "Generation completed" row.
-- ---------------------------------------------------------------------------
