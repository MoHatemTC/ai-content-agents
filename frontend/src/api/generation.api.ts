/** Generation endpoints (question bank, flashcards, study plan, revision, test help). */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import { getWorkspaceData } from "./workspace.api";
import type {
  FlashcardTopicsRequest,
  FlashcardTopicsResponse,
  GenerateFlashcardsRequest,
  GenerateFlashcardsResponse,
  GenerateQuestionsRequest,
  GenerateQuestionsResponse,
  GenerateRevisionSheetRequest,
  GenerateRevisionSheetResponse,
  GenerateStudyPlanRequest,
  GenerateStudyPlanResponse,
} from "@/types/api/generation.contracts";

const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}`;

export async function generateQuestions(
  req: GenerateQuestionsRequest,
): Promise<GenerateQuestionsResponse> {
  if (!isMockMode()) return http.post<GenerateQuestionsResponse>(paths.generation.questions, req);
  await delay(900);
  const data = await getWorkspaceData(req.workspaceId);
  const questions = data.questions.slice(0, req.count ?? 5);
  return {
    generationId: newId("gen"),
    kind: "question_bank",
    questions,
    grounding_score: 100,
    quality_score: 9.2,
  };
}

/** Test Help reuses the question generator with exam framing. */
export async function generateExam(
  req: GenerateQuestionsRequest,
): Promise<GenerateQuestionsResponse> {
  if (!isMockMode()) return http.post<GenerateQuestionsResponse>(paths.generation.testHelp, req);
  return generateQuestions(req);
}

export async function generateFlashcards(
  req: GenerateFlashcardsRequest,
): Promise<GenerateFlashcardsResponse> {
  if (!isMockMode()) return http.post<GenerateFlashcardsResponse>(paths.generation.flashcards, req);
  await delay(800);
  const data = await getWorkspaceData(req.workspaceId);
  const cards = data.flashcards.slice(0, req.count ?? 6);
  return {
    generationId: newId("gen"),
    kind: "flashcards",
    flashcards: cards.map((c, i) => ({
      front: c.front,
      back: c.back,
      format: req.cardFormat ?? "term-definition",
      topic: req.topic && req.topic !== "All chapters" ? req.topic : undefined,
      sourceChunkId: undefined,
      citations: [],
    })),
  };
}

export async function getFlashcardTopics(
  req: FlashcardTopicsRequest,
): Promise<FlashcardTopicsResponse> {
  if (!isMockMode()) {
    return http.post<FlashcardTopicsResponse>(paths.generation.flashcardTopics, req);
  }
  await delay(300);
  return {
    topics: ["Data types", "Variables & scope", "Control flow", "Functions", "OOP basics"],
  };
}

export interface StudyPlanDay {
  day: number;
  topics: string[];
  hours: number;
}

export async function generateStudyPlan(
  req: GenerateStudyPlanRequest & { days?: number; hoursPerDay?: number },
): Promise<GenerateStudyPlanResponse & { days: StudyPlanDay[] }> {
  if (!isMockMode()) {
    return http.post<GenerateStudyPlanResponse & { days: StudyPlanDay[] }>(
      paths.generation.studyPlan,
      req,
    );
  }
  await delay(900);
  const topics = [
    "Data types",
    "Variables & scope",
    "Control flow",
    "Functions",
    "Modules",
    "OOP basics",
    "Testing",
  ];
  const total = req.days ?? 7;
  const days: StudyPlanDay[] = Array.from({ length: total }, (_, i) => ({
    day: i + 1,
    topics: [topics[i % topics.length], topics[(i + 1) % topics.length]],
    hours: req.hoursPerDay ?? 2,
  }));
  return {
    generationId: newId("gen"),
    kind: "study_plan",
    summary: `${total}-day study plan`,
    sections: days.map((d) => ({ title: `Day ${d.day}`, items: d.topics })),
    days,
  };
}

export interface WeakTopic {
  topic: string;
  strength: number;
  action: string;
  description?: string;
  difficulty?: string;
  nextRevisionDate?: string;
  confidencePrompt?: string;
}

export async function generateRevisionSheet(
  req: GenerateRevisionSheetRequest,
): Promise<GenerateRevisionSheetResponse & { weakTopics: WeakTopic[] }> {
  if (!isMockMode()) {
    return http.post<GenerateRevisionSheetResponse & { weakTopics: WeakTopic[] }>(
      paths.generation.revision,
      req,
    );
  }
  await delay(800);
  const data = await getWorkspaceData(req.workspaceId);
  const weakTopics: WeakTopic[] = data.weakTopics.length
    ? data.weakTopics
    : [{ topic: "No signal yet", strength: 50, action: "Take a quiz in this workspace first" }];
  return {
    generationId: newId("gen"),
    kind: "revision_sheet",
    summary: "Weak topic revision sheet",
    sections: weakTopics.map((t) => ({ title: t.topic, items: [t.action] })),
    weakTopics,
  };
}
