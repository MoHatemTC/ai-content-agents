/** Generation history endpoints. */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import { getWorkspaceData } from "./workspace.api";
import type { WsHistoryRow } from "@/types/domain";
import type { GetHistoryResponse, HistoryQuery } from "@/types/api/generation.contracts";

export async function getHistory({ workspaceId }: HistoryQuery): Promise<GetHistoryResponse> {
  if (!isMockMode())
    return http.get<GetHistoryResponse>(`${paths.history}?workspace_id=${workspaceId}`);
  const data = await getWorkspaceData(workspaceId);
  return { history: data.history };
}

export async function appendHistory(workspaceId: string, row: WsHistoryRow): Promise<WsHistoryRow> {
  if (!isMockMode()) return http.post<WsHistoryRow>(paths.history, { workspaceId, row });
  await delay(40);
  return row;
}
