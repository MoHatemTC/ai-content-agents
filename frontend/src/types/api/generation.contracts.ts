import type { GeneratedQuestion } from "@/types/domain";
import type { WsFlashcard, WsHistoryRow } from "@/types/domain";
import type { GenerationKind } from "@/types/database.types";

export interface GenerationBaseRequest {
  workspaceId: string;
  documentIds: string[];
  model: string;
  /** Free-form agent controls from the studio panels. */
  options?: Record<string, unknown>;
}

export interface GenerateQuestionsRequest extends GenerationBaseRequest {
  count?: number;
  difficulty?: string;
  types?: string[];
}

export interface GenerateQuestionsResponse {
  generationId: string;
  kind: Extract<GenerationKind, "question_bank">;
  questions: GeneratedQuestion[];
  grounding_score: number;
  quality_score: number;
}

export interface GenerateFlashcardsRequest extends GenerationBaseRequest {
  count?: number;
  /** "term-definition" (front = term) or "qa" (front = question). */
  cardFormat?: "term-definition" | "qa";
  /** Real topic from the PDF; "All chapters" (default) means the whole doc. */
  topic?: string;
}

export interface GenerateFlashcardsResponse {
  generationId: string;
  kind: Extract<GenerationKind, "flashcards">;
  flashcards: WsFlashcard[];
}

export type FlashcardTopicsRequest = GenerationBaseRequest;

export interface FlashcardTopicsResponse {
  topics: string[];
}

export interface GenerateStudyPlanRequest extends GenerationBaseRequest {
  weeks?: number;
  hoursPerWeek?: number;
}

export interface GenerateStudyPlanResponse {
  generationId: string;
  kind: Extract<GenerationKind, "study_plan">;
  summary: string;
  sections: { title: string; items: string[] }[];
}

export interface GenerateRevisionSheetRequest extends GenerationBaseRequest {
  topics?: string[];
}

export interface GenerateRevisionSheetResponse {
  generationId: string;
  kind: Extract<GenerationKind, "revision_sheet">;
  summary: string;
  sections: { title: string; items: string[] }[];
}

export interface HistoryQuery {
  workspaceId: string;
  kind?: GenerationKind;
}

export interface GetHistoryResponse {
  history: WsHistoryRow[];
}
