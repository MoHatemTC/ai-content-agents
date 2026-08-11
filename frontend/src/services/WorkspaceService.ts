/** Workspace business logic. */
import * as workspaceApi from "@/api/workspace.api";
import * as supabaseApi from "@/api/supabase.api";
import { isMockMode } from "@/config/env";
import { logger } from "@/lib/logger";
import { supabase } from "@/lib/supabase";
import { attempt } from "@/lib/result";
import type { Result } from "@/types/api/common";
import type { BootstrapWorkspacesResponse } from "@/types/api/workspace.contracts";
import type { DbGeneration, ReviewStatus } from "@/types/database.types";
import type { ReviewState, Workspace, WorkspaceData, WsHistoryRow } from "@/types/domain";
import { KIND_TO_AGENT } from "@/services/HistoryService";

const STATUS_TO_REVIEW: Record<ReviewStatus, ReviewState> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_edit: "Needs Edit",
};

/** Number of generated items stored in a generation payload, by kind. */
function countItems(g: DbGeneration): number {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  for (const key of ["questions", "flashcards", "days", "weakTopics"]) {
    const value = payload[key];
    if (Array.isArray(value)) return value.length;
  }
  return 0;
}

function generationToHistoryRow(g: DbGeneration): WsHistoryRow {
  return {
    id: g.id,
    date: (g.created_at ?? "").slice(0, 16).replace("T", " "),
    agent: KIND_TO_AGENT[g.kind] ?? g.kind,
    doc: g.title || g.kind,
    status: "Completed",
    quality: g.quality_score ?? 0,
    review: STATUS_TO_REVIEW[g.review_status] ?? "Pending",
    items: countItems(g),
    generationId: g.id,
  };
}

/** Merge the Supabase-backed run log over the FastAPI bootstrap store. */
async function mergeSupabaseHistory(
  workspaces: Workspace[],
  store: Record<string, WorkspaceData>,
): Promise<void> {
  const generations = await supabaseApi.listGenerationsForWorkspaces(workspaces.map((w) => w.id));
  const byWorkspace = new Map<string, DbGeneration[]>();
  for (const g of generations) {
    const rows = byWorkspace.get(g.workspace_id) ?? [];
    rows.push(g);
    byWorkspace.set(g.workspace_id, rows);
  }
  for (const w of workspaces) {
    const rows = (byWorkspace.get(w.id) ?? []).map(generationToHistoryRow);
    // The Supabase log is authoritative for runs persisted since Phase 8; the
    // FastAPI history table only carries legacy rows, so overlay on top.
    store[w.id] = { ...store[w.id], history: rows.length ? rows : store[w.id].history };
  }
}

export const WorkspaceService = {
  /** Workspaces + their scoped data — used to hydrate the workspace provider. */
  async bootstrap(): Promise<Result<BootstrapWorkspacesResponse>> {
    return attempt("WorkspaceService.bootstrap", async () => {
      const base = await workspaceApi.getWorkspaceBootstrap();
      if (isMockMode()) return base;

      // Mirror FastAPI workspaces into Supabase so the FK-linking tables
      // (`generations`, `history`, `reviews`) resolve. FastAPI already scopes
      // the list to the signed-in user, and RLS makes the row owner the
      // Supabase `auth.uid()`, so every mirrored row is "own".
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (user) {
        await supabaseApi.syncWorkspaces(
          base.workspaces.map((w) => ({
            id: w.id,
            owner_id: user.id,
            name: w.name,
            subject: w.subject,
            description: w.description ?? null,
            accent: w.accent ?? null,
          })),
        );
      }

      await mergeSupabaseHistory(base.workspaces, base.store);
      return base;
    });
  },

  async listWorkspaces(): Promise<Result<Workspace[]>> {
    return attempt(
      "WorkspaceService.listWorkspaces",
      async () => (await workspaceApi.getWorkspaces()).workspaces,
    );
  },

  async getWorkspace(id: string): Promise<Result<{ workspace: Workspace; data: WorkspaceData }>> {
    return attempt("WorkspaceService.getWorkspace", () => workspaceApi.getWorkspace(id));
  },

  async getWorkspaceData(id: string): Promise<Result<WorkspaceData>> {
    return attempt("WorkspaceService.getWorkspaceData", () => workspaceApi.getWorkspaceData(id));
  },

  async createWorkspace(input: { name: string; description: string }): Promise<Result<Workspace>> {
    return attempt("WorkspaceService.createWorkspace", async () => {
      const { workspace } = await workspaceApi.createWorkspace(input);
      if (!isMockMode()) {
        // Mirror immediately so generations FKs resolve even before the next
        // bootstrap refresh (RLS scopes the row to the signed-in user).
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user) {
          await supabaseApi.syncWorkspaces([
            {
              id: workspace.id,
              owner_id: user.id,
              name: workspace.name,
              subject: workspace.subject,
              description: workspace.description ?? null,
              accent: workspace.accent ?? null,
            },
          ]);
        }
      }
      return workspace;
    });
  },

  async updateWorkspace(
    input: Parameters<typeof workspaceApi.updateWorkspace>[0],
  ): Promise<Result<void>> {
    return attempt("WorkspaceService.updateWorkspace", async () => {
      await workspaceApi.updateWorkspace(input);
      if (!isMockMode()) {
        // FastAPI is the source of truth; keep the Supabase mirror (the FK
        // target for generations/history) in step. Best-effort: a Supabase
        // hiccup must never fail a rename that already succeeded in FastAPI.
        try {
          await supabaseApi.updateWorkspaceMirror(input.id, input.patch);
        } catch (error) {
          logger.warn(
            "Supabase workspace mirror update failed",
            error instanceof Error ? error.message : String(error),
          );
        }
      }
    });
  },

  async removeWorkspace(id: string): Promise<Result<void>> {
    return attempt("WorkspaceService.removeWorkspace", async () => {
      await workspaceApi.deleteWorkspace(id);
      if (!isMockMode()) {
        try {
          await supabaseApi.deleteWorkspaceMirror(id);
        } catch (error) {
          logger.warn(
            "Supabase workspace mirror delete failed",
            error instanceof Error ? error.message : String(error),
          );
        }
      }
    });
  },

  /** Ensures a workspace id is unique against the ids already known locally. */
  uniqueId(name: string, taken: string[]): string {
    const base = workspaceApi.slugifyWorkspaceName(name) || `workspace-${Date.now()}`;
    return taken.includes(base) ? `${base}-${Date.now().toString(36).slice(-4)}` : base;
  },
};
