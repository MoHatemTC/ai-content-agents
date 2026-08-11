/**
 * AI provider abstraction.
 *
 * The UI selects a provider id; it never learns whether the answer came from a
 * local mock, Gemini, Kimi or Nvidia. Each provider currently delegates to the
 * mock-backed API layer; later each maps to its FastAPI route.
 */
import * as chatApi from "@/api/chat.api";
import * as generationApi from "@/api/generation.api";
import type { MentorChatRequest, MentorChatResponse } from "@/types/api/chat.contracts";
import type {
  FlashcardTopicsRequest,
  FlashcardTopicsResponse,
  GenerateFlashcardsRequest,
  GenerateFlashcardsResponse,
  GenerateQuestionsRequest,
  GenerateQuestionsResponse,
  GenerateRevisionSheetRequest,
  GenerateStudyPlanRequest,
} from "@/types/api/generation.contracts";

export interface ChatContext {
  docTitle: string;
  workspaceName: string;
}

export interface AIProvider {
  id: string;
  label: string;
  vendor: string;
  generateQuestions(req: GenerateQuestionsRequest): Promise<GenerateQuestionsResponse>;
  generateExam(req: GenerateQuestionsRequest): Promise<GenerateQuestionsResponse>;
  generateFlashcards(req: GenerateFlashcardsRequest): Promise<GenerateFlashcardsResponse>;
  flashcardTopics(req: FlashcardTopicsRequest): Promise<FlashcardTopicsResponse>;
  generateStudyPlan(
    req: GenerateStudyPlanRequest & { days?: number; hoursPerDay?: number },
  ): ReturnType<typeof generationApi.generateStudyPlan>;
  generateRevisionSheet(
    req: GenerateRevisionSheetRequest,
  ): ReturnType<typeof generationApi.generateRevisionSheet>;
  mentorChat(req: MentorChatRequest, ctx: ChatContext): Promise<MentorChatResponse>;
  conceptChat(req: MentorChatRequest, ctx: ChatContext): Promise<MentorChatResponse>;
}

function createProvider(id: string, label: string, vendor: string): AIProvider {
  return {
    id,
    label,
    vendor,
    generateQuestions: (req) => generationApi.generateQuestions({ ...req, model: id }),
    generateExam: (req) => generationApi.generateExam({ ...req, model: id }),
    generateFlashcards: (req) => generationApi.generateFlashcards({ ...req, model: id }),
    flashcardTopics: (req) => generationApi.getFlashcardTopics({ ...req, model: id }),
    generateStudyPlan: (req) => generationApi.generateStudyPlan({ ...req, model: id }),
    generateRevisionSheet: (req) => generationApi.generateRevisionSheet({ ...req, model: id }),
    mentorChat: (req, ctx) => chatApi.generateMentorResponse({ ...req, model: id }, ctx),
    conceptChat: (req, ctx) => chatApi.generateConceptResponse({ ...req, model: id }, ctx),
  };
}

export const MockProvider = createProvider("mock", "Mock", "Local");
export const GeminiProvider = createProvider("gemini", "Gemini 1.5", "Google");
export const KimiProvider = createProvider("kimi", "Kimi K2", "Moonshot");
export const NvidiaProvider = createProvider("nvidia", "Nvidia Nemotron", "OpenRouter");

const REGISTRY: Record<string, AIProvider> = {
  mock: MockProvider,
  gemini: GeminiProvider,
  kimi: KimiProvider,
  nvidia: NvidiaProvider,
};

export function getProvider(id: string | undefined): AIProvider {
  return (id && REGISTRY[id]) || MockProvider;
}

export const listProviders = () => Object.values(REGISTRY);
