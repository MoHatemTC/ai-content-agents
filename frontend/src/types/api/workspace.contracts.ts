import type { Workspace } from "@/types/domain";
import type { WorkspaceData } from "@/types/domain";

export interface CreateWorkspaceRequest {
  name: string;
  description: string;
}

export interface CreateWorkspaceResponse {
  workspace: Workspace;
}

export interface GetWorkspacesResponse {
  workspaces: Workspace[];
}

export interface GetWorkspaceResponse {
  workspace: Workspace;
  data: WorkspaceData;
}

export interface UpdateWorkspaceRequest {
  id: string;
  patch: Partial<Pick<Workspace, "name" | "description" | "subject">>;
}

export interface BootstrapWorkspacesResponse {
  workspaces: Workspace[];
  /** Workspace-scoped payloads keyed by workspace id. */
  store: Record<string, WorkspaceData>;
}
