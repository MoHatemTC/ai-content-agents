/**
 * Generation business logic. Every generator panel calls this service —
 * no component builds content itself.
 */
import { getProvider } from "./ai/AIProvider";
import { attempt } from "@/lib/result";
import type { Result } from "@/types/api/common";
import type { Flashcard } from "@/components/app/FlashcardDeck";
import type { GeneratedQuestion } from "@/types/domain";
import type { StudyPlanDay, WeakTopic } from "@/api/generation.api";

interface BaseInput {
  workspaceId: string;
  documentId: string;
  model: string;
}

export const GenerationService = {
  async generateQuestions(
    input: BaseInput & { count: number; type?: string; difficulty?: string },
  ): Promise<Result<GeneratedQuestion[]>> {
    return attempt("GenerationService.generate", async () => {
      const res = await getProvider(input.model).generateQuestions({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
        count: input.count,
        difficulty: input.difficulty,
        types: input.type ? [input.type] : undefined,
      });
      return res.questions;
    });
  },

  async generateExam(
    input: BaseInput & { count: number; durationMinutes: number },
  ): Promise<Result<GeneratedQuestion[]>> {
    return attempt("GenerationService.generate", async () => {
      const res = await getProvider(input.model).generateExam({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
        count: input.count,
        options: { durationMinutes: input.durationMinutes },
      });
      return res.questions;
    });
  },

  async generateFlashcards(
    input: BaseInput & { count: number; topic: string; format?: "term-definition" | "qa" },
  ): Promise<Result<Flashcard[]>> {
    return attempt("GenerationService.generate", async () => {
      const res = await getProvider(input.model).generateFlashcards({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
        count: input.count,
        cardFormat: input.format,
        topic: input.topic,
      });
      return res.flashcards.map((c, i) => ({
        id: `card-${i}`,
        front: c.front,
        back: c.back,
        topic: c.topic ?? input.topic,
        format: c.format,
        citations: c.citations,
      }));
    });
  },

  async flashcardTopics(input: BaseInput): Promise<Result<string[]>> {
    return attempt("GenerationService.flashcardTopics", async () => {
      const res = await getProvider(input.model).flashcardTopics({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
      });
      return res.topics;
    });
  },

  async generateStudyPlan(
    input: BaseInput & { days: number; hoursPerDay: number },
  ): Promise<Result<StudyPlanDay[]>> {
    return attempt("GenerationService.generate", async () => {
      const res = await getProvider(input.model).generateStudyPlan({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
        days: input.days,
        hoursPerDay: input.hoursPerDay,
      });
      return res.days;
    });
  },

  async generateRevisionSheet(input: BaseInput): Promise<Result<WeakTopic[]>> {
    return attempt("GenerationService.generate", async () => {
      const res = await getProvider(input.model).generateRevisionSheet({
        workspaceId: input.workspaceId,
        documentIds: [input.documentId].filter(Boolean),
        model: input.model,
      });
      return res.weakTopics;
    });
  },
};
