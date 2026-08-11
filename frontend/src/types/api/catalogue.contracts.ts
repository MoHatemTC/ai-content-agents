/** Catalogue endpoints: agents, pipeline stages, notifications, search. */
import type {
  Agent,
  AppNotification,
  DocItem,
  HistoryItem,
  PipelineStep,
  RagStage,
  SearchResult,
  WsFlashcard,
} from "@/types/domain";

export interface ListAgentsResponse {
  agents: Agent[];
}

export interface GetAgentResponse {
  agent: Agent;
}

export interface ListPipelineStepsResponse {
  steps: PipelineStep[];
  /** How many stages have completed for the current workspace. */
  completed: number;
}

export interface ListRagStagesResponse {
  stages: RagStage[];
}

export interface ListNotificationsQuery {
  role?: "student" | "reviewer" | "admin";
}

export interface ListNotificationsResponse {
  notifications: AppNotification[];
  unread: number;
}

export interface CatalogueResponse {
  documents: DocItem[];
  history: HistoryItem[];
  flashcards: WsFlashcard[];
}

export interface SearchQuery {
  q: string;
  workspaceId?: string;
  kinds?: SearchResult["kind"][];
  limit?: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
}
