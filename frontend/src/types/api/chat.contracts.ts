import type { WsChatMessage } from "@/types/domain";
import type { ChatKind } from "@/types/database.types";

export interface CreateChatRequest {
  workspaceId: string;
  kind: ChatKind;
  title: string;
  model: string;
}

export interface CreateChatResponse {
  chatId: string;
}

export interface MentorChatRequest {
  workspaceId: string;
  chatId: string;
  message: string;
  model: string;
  documentIds?: string[];
}

export interface MentorChatResponse {
  message: WsChatMessage;
  /** Chunks the answer was grounded on. */
  citations: { docId: string; docTitle: string; page?: number; snippet: string }[];
}

export type ConceptChatRequest = MentorChatRequest;
export type ConceptChatResponse = MentorChatResponse;
