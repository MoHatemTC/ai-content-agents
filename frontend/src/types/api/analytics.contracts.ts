import type { ActivityPoint, DistributionBucket, TopicCoverage } from "@/types/domain";

export interface AnalyticsQuery {
  workspaceId: string;
  range?: "7d" | "30d" | "90d";
}

/** Live platform aggregates shown on the analytics stat cards. */
export interface AnalyticsSummary {
  /** Question items generated (question_bank + test_help). */
  questions: number;
  /** Flashcard items generated (flashcards). */
  flashcards: number;
  /** Study plans generated. */
  studyPlans: number;
  /** Mean grounding score (0–100), null when nothing is scored yet. */
  grounding: number | null;
  /** Mean quality score (0–10), null when nothing is scored yet. */
  quality: number | null;
  /** % of reviewable generations that left `pending` (0–100), null when none. */
  reviewCompletion: number | null;
}

export interface AnalyticsResponse {
  /** Distribution of generated items across Bloom levels. */
  bloomDistribution: DistributionBucket[];
  /** Distribution across question types (MCQ, True/False, …). */
  typeDistribution: DistributionBucket[];
  /** Weekly generation activity. */
  activitySeries: ActivityPoint[];
  /** Syllabus coverage per topic. */
  topicCoverage: TopicCoverage[];
  /** Live site-wide aggregates for the stat cards. */
  summary: AnalyticsSummary;
}

export interface ModelInfo {
  id: string;
  name: string;
  vendor: string;
  desc: string;
  available: boolean;
}

export interface GetModelsResponse {
  models: ModelInfo[];
}
