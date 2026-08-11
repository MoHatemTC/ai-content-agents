/** Workspace endpoints.
 *
 * Real mode talks to the FastAPI backend (the single source of truth for
 * workspace records) via the shared `http` client, which attaches the Supabase
 * access token automatically. Mock mode returns local fixtures.
 */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import { getDocumentsForWorkspaces } from "./document.api";
import { workspaces as seedWorkspaces } from "@/mock/studio-data";
import type { ReviewState, Workspace, WorkspaceAccent, WorkspaceData } from "@/types/domain";
import type {
  CreateWorkspaceRequest,
  CreateWorkspaceResponse,
} from "@/types/api/workspace.contracts";
import type {
  BootstrapWorkspacesResponse,
  GetWorkspaceResponse,
  GetWorkspacesResponse,
  UpdateWorkspaceRequest,
} from "@/types/api/workspace.contracts";

const ACCENTS: WorkspaceAccent[] = ["primary", "info", "success", "warning"];

const REVIEW_STATES: Record<string, ReviewState> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_edit: "Needs Edit",
};

/**
 * Map a backend row to the fully-shaped UI model.
 *
 * The backend row may be missing the extra read-model fields the UI renders
 * (`owner`, `generations`, `reviewStatus`, `lastActive`); those are derived
 * with safe defaults so the backend stays the source of truth.
 */
function mapWorkspace(row: Workspace): Workspace {
  const accent = ACCENTS.includes(row.accent) ? row.accent : "primary";
  return {
    id: String(row.id),
    name: String(row.name ?? ""),
    subject: String(row.subject ?? ""),
    description: (row.description as string | null) ?? undefined,
    docs: Number(row.docs ?? 0),
    assets: Number(row.assets ?? 0),
    pendingReview: Number(row.pendingReview ?? 0),
    generations: Number(row.generations ?? 0),
    reviewStatus: (REVIEW_STATES[String(row.reviewStatus)] ?? "Pending") as ReviewState,
    lastActive: (row.lastActive as string | undefined) ?? "Just now",
    accent,
    owner: {
      id: String(row.owner?.id ?? ""),
      name: (row.owner?.name as string | undefined) ?? "You",
      email: (row.owner?.email as string | undefined) ?? "",
    },
  };
}

export async function getWorkspaces(): Promise<GetWorkspacesResponse> {
  if (isMockMode()) {
    await delay(60);
    return { workspaces: seedWorkspaces };
  }
  const res = await http.get<GetWorkspacesResponse>(paths.workspaces.list);
  return { ...res, workspaces: (res.workspaces ?? []).map(mapWorkspace) };
}

export async function getWorkspace(id: string): Promise<GetWorkspaceResponse> {
  if (isMockMode()) {
    await delay(60);
    const workspace = seedWorkspaces.find((w) => w.id === id) ?? seedWorkspaces[0];
    return {
      workspace,
      data: {
        docs: [],
        questions: [],
        flashcards: [],
        chats: [],
        history: [],
        weakTopics: [],
        audit: [],
      },
    };
  }
  return http.get<GetWorkspaceResponse>(paths.workspaces.detail(id)).then((res) => ({
    ...res,
    workspace: mapWorkspace(res.workspace!),
  }));
}

export function slugifyWorkspaceName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export async function createWorkspace(
  input: CreateWorkspaceRequest,
): Promise<CreateWorkspaceResponse> {
  if (!isMockMode()) {
    const res = await http.post<CreateWorkspaceResponse>(paths.workspaces.list, {
      name: input.name.trim(),
      description: input.description?.trim() || null,
    });
    return { ...res, workspace: mapWorkspace(res.workspace!) };
  }
  await delay(80);
  const id = slugifyWorkspaceName(input.name) || `workspace-${Date.now()}`;
  return {
    workspace: {
      id,
      name: input.name.trim(),
      subject: input.description.trim() || "New workspace",
      description: input.description.trim(),
      docs: 0,
      assets: 0,
      pendingReview: 0,
      generations: 0,
      reviewStatus: "Pending",
      lastActive: "Just now",
      accent: "primary",
      owner: { id: "", name: "You", email: "" },
    } as Workspace,
  };
}

export async function updateWorkspace({ id, patch }: UpdateWorkspaceRequest): Promise<void> {
  if (isMockMode()) {
    await delay(50);
    return;
  }
  await http.patch<void>(paths.workspaces.detail(id), patch);
}

export async function deleteWorkspace(id: string): Promise<void> {
  if (isMockMode()) {
    await delay(50);
    return;
  }
  await http.delete<void>(paths.workspaces.detail(id));
}

export async function getWorkspaceData(id: string): Promise<WorkspaceData> {
  const res = await getWorkspace(id);
  return (
    res.data ?? {
      docs: [],
      questions: [],
      flashcards: [],
      chats: [],
      history: [],
      weakTopics: [],
      audit: [],
    }
  );
}

/** GET /workspaces + GET /documents per workspace — the bootstrap payload. */
export async function getWorkspaceBootstrap(): Promise<BootstrapWorkspacesResponse> {
  if (isMockMode()) {
    await delay(220);
    const store: Record<string, WorkspaceData> = {};
    for (const w of seedWorkspaces) {
      store[w.id] = {
        docs: [],
        questions: [],
        flashcards: [],
        chats: [],
        history: [],
        weakTopics: [],
        audit: [],
      };
    }
    return { workspaces: seedWorkspaces, store };
  }
  const { workspaces } = await getWorkspaces();
  const ids = workspaces.map((w) => w.id);
  const [docsByWorkspace, chatsByWorkspace, historyByWorkspace] = await Promise.all([
    getDocumentsForWorkspaces(ids),
    Promise.all(
      ids.map(async (id) => {
        try {
          return (await import("./chat.api")).getChats(id);
        } catch {
          return { chats: [] };
        }
      }),
    ),
    Promise.all(
      ids.map(async (id) => {
        try {
          return await (await import("./history.api")).getHistory({ workspaceId: id });
        } catch {
          return { history: [] };
        }
      }),
    ),
  ]);
  const store: Record<string, WorkspaceData> = {};
  for (let i = 0; i < workspaces.length; i++) {
    const w = workspaces[i];
    store[w.id] = {
      docs: docsByWorkspace[w.id] ?? [],
      questions: [],
      flashcards: [],
      chats: chatsByWorkspace[i]?.chats ?? [],
      history: historyByWorkspace[i]?.history ?? [],
      weakTopics: [],
      audit: [],
    };
  }
  return { workspaces, store };
}
