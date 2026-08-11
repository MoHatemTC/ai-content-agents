import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { emptyWorkspaceData } from "@/lib/workspace";
import { supabase } from "@/lib/supabase";
import { isMockMode } from "@/config/env";
import { logger } from "@/lib/logger";
import { useAuth } from "@/contexts/AuthContext";
import { DocumentService, HistoryService, WorkspaceService } from "@/services";
import type { PersistGenerationMeta } from "@/services/HistoryService";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { ErrorState, LoadingState } from "@/components/app/AsyncState";
import type {
  ReviewState,
  Workspace,
  WorkspaceData,
  WsAuditEntry,
  WsChat,
  WsDoc,
  WsHistoryRow,
} from "@/types/domain";

import { STORAGE_KEYS } from "@/constants";

const STORAGE_KEY = STORAGE_KEYS.workspaceActive;
const STATE_KEY = STORAGE_KEYS.workspaceState;

interface PersistShape {
  activeId: string | null;
  workspaces: Workspace[];
  store: Record<string, WorkspaceData>;
}

interface WorkspaceCtx {
  workspaces: Workspace[];
  /** The active workspace — null until the user creates their first one. */
  active: Workspace | null;
  setActive: (id: string) => void;
  addWorkspace: (input: { name: string; description: string }) => Promise<Workspace>;
  /** Rename / re-describe a workspace. */
  updateWorkspace: (id: string, patch: { name?: string; description?: string }) => Promise<void>;
  /** Remove a workspace (owner + admin) and its local data. */
  removeWorkspace: (id: string) => Promise<void>;
  /** Refetch the workspace list from the server. */
  refreshWorkspaces: () => void;
  /** Data scoped to the active workspace — switching swaps everything. */
  data: WorkspaceData;
  /** Persist a new document (text note or staged upload) and add it to the store. */
  addDoc: (doc: WsDoc) => Promise<void>;
  updateDoc: (id: string, patch: Partial<WsDoc>) => void;
  removeDoc: (id: string) => void;
  /** Review + audit */
  setReview: (
    itemId: string,
    state: ReviewState,
    opts?: { comment?: string; actor?: string; label?: string },
  ) => void;
  addAudit: (entry: Omit<WsAuditEntry, "id" | "at"> & { at?: string }) => void;
  /** Workspace-scoped write-back */
  addChat: (chat: WsChat) => void;
  appendChatMessage: (chatId: string, message: WsChat["messages"][number]) => void;
  addHistory: (row: WsHistoryRow, meta?: PersistGenerationMeta) => void;
}

const Ctx = createContext<WorkspaceCtx | null>(null);

function nowStamp() {
  return new Date().toISOString().slice(0, 16).replace("T", " ");
}

/**
 * Loads workspaces through `WorkspaceService`, then renders the provider.
 * Keeps the provider itself free of any mock/seed import.
 */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const queryClient = useQueryClient();
  const { data, isPending, error, refetch } = useServiceQuery(
    ["workspace-bootstrap", user?.id ?? null],
    () => WorkspaceService.bootstrap(),
    {
      refetchOnWindowFocus: true,
      // Never fire the authenticated request until the session is restored AND
      // a user is present; otherwise we'd send a tokenless 401 up front. The
      // bootstrapping is keyed on the user id once the session settles.
      enabled: ready && !!user?.id,
    },
  );

  // Realtime: when a workspace row the current user can see changes, refresh
  // ONLY the workspace-bootstrap cache (never the whole query cache). RLS on
  // the subscribed table filters delivered events to this user's workspaces.
  useEffect(() => {
    if (isMockMode() || !user) return;
    const channel = supabase
      .channel(`workspace-updates-${user.id}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "workspaces" }, () => {
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [user, queryClient]);

  // Signed out: don't hit the API. Give the tree an empty store so the routes
  // below can render, and let a RoleGate redirect to /login.
  if (ready && !user) {
    return (
      <WorkspaceStore seedWorkspaces={[]} seedStore={{}}>
        {children}
      </WorkspaceStore>
    );
  }

  if (isPending) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <LoadingState label="Loading your workspaces…" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center px-6">
        <ErrorState
          title="Unable to load your workspaces"
          message={error?.message ?? "Please try again."}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <WorkspaceStore seedWorkspaces={data.workspaces} seedStore={data.store}>
      {children}
    </WorkspaceStore>
  );
}

function WorkspaceStore({
  seedWorkspaces,
  seedStore,
  children,
}: {
  seedWorkspaces: Workspace[];
  seedStore: Record<string, WorkspaceData>;
  children: ReactNode;
}) {
  const [activeId, setActiveId] = useState<string | null>(seedWorkspaces[0]?.id ?? null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>(seedWorkspaces);
  const [store, setStore] = useState<Record<string, WorkspaceData>>(seedStore);
  const hydrated = useRef(false);
  const queryClient = useQueryClient();

  // Restore persisted UI state after hydration. The workspace LIST always comes
  // from the server (seedWorkspaces) — a stale local copy must never override
  // it. Only the active id and per-workspace draft data are restored, scoped to
  // workspaces that still exist on the server.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STATE_KEY);
      const parsed = raw ? (JSON.parse(raw) as PersistShape) : null;
      const ids = new Set(seedWorkspaces.map((w) => w.id));
      if (parsed) {
        if (parsed.store) {
          // The generation run log is not persisted locally anymore (Phase 8):
          // restore only the draft fields (notes, chats, audit, review state)
          // from the local snapshot and KEEP the Supabase-backed run log that
          // the bootstrap just fetched. Overwriting the whole store would wipe
          // history on every reload.
          const next: Record<string, WorkspaceData> = {};
          for (const id of ids) {
            const seed = seedStore[id];
            if (!seed) continue;
            const local = parsed.store[id];
            next[id] = local ? { ...local, history: seed.history } : seed;
          }
          setStore(next);
        }
        if (parsed.activeId && ids.has(parsed.activeId)) setActiveId(parsed.activeId);
      } else {
        const legacy = window.localStorage.getItem(STORAGE_KEY);
        if (legacy && ids.has(legacy)) setActiveId(legacy);
      }
    } catch {
      /* ignore */
    }
    hydrated.current = true;
  }, [seedWorkspaces, seedStore]);

  // The server list is authoritative: whenever the bootstrap query refreshes
  // (window focus, reconnect, or invalidation after a mutation), propagate it
  // into state so workspaces deleted outside the app disappear immediately.
  useEffect(() => {
    setWorkspaces(seedWorkspaces);
  }, [seedWorkspaces]);

  // Persist everything so notes, chats and review history survive a reload.
  // The generation run log is excluded: since Phase 8 it lives in Supabase
  // (`generations` + `history`) and is re-fetched at bootstrap.
  useEffect(() => {
    if (!hydrated.current) return;
    try {
      const withoutHistory = Object.fromEntries(
        Object.entries(store).map(([id, d]) => [id, { ...d, history: [] }]),
      );
      window.localStorage.setItem(
        STATE_KEY,
        JSON.stringify({ activeId, workspaces, store: withoutHistory } satisfies PersistShape),
      );
      window.localStorage.setItem(STORAGE_KEY, activeId ?? "");
    } catch {
      /* ignore */
    }
  }, [activeId, workspaces, store]);

  const setActive = useCallback(
    (id: string) => {
      // Ignore ids that don't exist — nothing to activate when the list is empty.
      setActiveId((prev) => (workspaces.some((w) => w.id === id) ? id : prev));
    },
    [workspaces],
  );

  const mutate = useCallback(
    (id: string, fn: (d: WorkspaceData) => WorkspaceData) =>
      setStore((prev) => ({ ...prev, [id]: fn(prev[id] ?? emptyWorkspaceData()) })),
    [],
  );

  const value = useMemo<WorkspaceCtx>(() => {
    const active = workspaces.find((w) => w.id === activeId) ?? workspaces[0] ?? null;
    const raw = active ? (store[active.id] ?? emptyWorkspaceData()) : emptyWorkspaceData();
    const data: WorkspaceData = { ...raw, audit: raw.audit ?? [] };

    const pushAudit = (d: WorkspaceData, entry: WsAuditEntry): WorkspaceData => ({
      ...d,
      audit: [entry, ...(d.audit ?? [])],
    });

    return {
      workspaces,
      active,
      setActive,
      refreshWorkspaces: () => {
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
      },
      addWorkspace: async ({ name, description }) => {
        const result = await WorkspaceService.createWorkspace({ name, description });
        if (!result.success) throw new Error(result.error.message);
        const workspace = result.data;
        setWorkspaces((prev) => [...prev, workspace]);
        setStore((prev) => ({ ...prev, [workspace.id]: emptyWorkspaceData() }));
        setActiveId(workspace.id);
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
        return workspace;
      },
      updateWorkspace: async (id, patch) => {
        const result = await WorkspaceService.updateWorkspace({ id, patch });
        if (!result.success) throw new Error(result.error.message);
        setWorkspaces((prev) => prev.map((w) => (w.id === id ? { ...w, ...patch } : w)));
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
      },
      removeWorkspace: async (id) => {
        const result = await WorkspaceService.removeWorkspace(id);
        if (!result.success) throw new Error(result.error.message);
        const remaining = workspaces.filter((w) => w.id !== id);
        setWorkspaces(remaining);
        setStore((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        if (activeId === id) setActiveId(remaining[0]?.id ?? null);
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
      },
      data,
      addDoc: async (doc) => {
        if (!active) return;
        const persisted = await DocumentService.createDocument(active.id, doc);
        mutate(active.id, (d) => ({
          ...d,
          docs: [persisted, ...d.docs.filter((x) => x.id !== persisted.id)],
        }));
        void queryClient.invalidateQueries({ queryKey: ["workspace-bootstrap"] });
      },
      updateDoc: (id, patch) => {
        if (!active) return;
        mutate(active.id, (d) => ({
          ...d,
          docs: d.docs.map((x) => (x.id === id ? { ...x, ...patch } : x)),
        }));
        void DocumentService.updateDocument(active.id, id, patch).catch((err) =>
          logger.warn("Failed to persist document update", err),
        );
      },
      removeDoc: (id) => {
        if (!active) return;
        mutate(active.id, (d) => ({ ...d, docs: d.docs.filter((x) => x.id !== id) }));
        void DocumentService.deleteDocument(id).catch((err) =>
          logger.warn("Failed to persist document deletion", err),
        );
      },
      setReview: (itemId, state, opts) => {
        if (!active) return;
        mutate(active.id, (d) => {
          const item = d.questions.find((q) => q.id === itemId);
          const next: WorkspaceData = {
            ...d,
            questions: d.questions.map((q) => (q.id === itemId ? { ...q, review: state } : q)),
            history: d.history.map((h) => (h.id === itemId ? { ...h, review: state } : h)),
          };
          return pushAudit(next, {
            id: `aud-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            itemId,
            itemLabel: opts?.label ?? item?.prompt ?? itemId,
            action: state === "Pending" ? "Flagged" : (state as WsAuditEntry["action"]),
            actor: opts?.actor ?? "You",
            at: nowStamp(),
            comment: opts?.comment,
          });
        });
      },
      addAudit: (entry) => {
        if (!active) return;
        mutate(active.id, (d) =>
          pushAudit(d, {
            ...entry,
            id: `aud-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            at: entry.at ?? nowStamp(),
          }),
        );
      },
      addChat: (chat) => {
        if (!active) return;
        mutate(active.id, (d) => ({ ...d, chats: [chat, ...d.chats] }));
      },
      appendChatMessage: (chatId, message) => {
        if (!active) return;
        mutate(active.id, (d) => ({
          ...d,
          chats: d.chats.map((c) =>
            c.id === chatId ? { ...c, messages: [...c.messages, message] } : c,
          ),
        }));
      },
      addHistory: (row, meta) => {
        if (!active) return;
        mutate(active.id, (d) => ({ ...d, history: [row, ...d.history] }));
        if (meta?.kind) {
          // Phase 8: generations live in Supabase (payload + review queue).
          void HistoryService.appendSupabase(active.id, row, meta).catch((err) =>
            logger.error("Failed to persist generation to Supabase", err),
          );
        } else {
          // Legacy FastAPI run log (mock mode / plain session rows).
          void HistoryService.append(active.id, row).catch((err) =>
            logger.warn("Failed to persist history row", err),
          );
        }
      },
    };
  }, [
    activeId,
    queryClient,
    setActive,
    store,
    mutate,
    workspaces,
    setStore,
    setWorkspaces,
    setActiveId,
  ]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}
