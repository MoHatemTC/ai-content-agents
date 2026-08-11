/** Analytics business logic. */
import * as adminApi from "@/api/admin.api";
import * as supabaseApi from "@/api/supabase.api";
import { isMockMode } from "@/config/env";
import { attempt } from "@/lib/result";
import type {
  AnalyticsQuery,
  AnalyticsResponse,
  AnalyticsSummary,
} from "@/types/api/analytics.contracts";
import type { Result } from "@/types/api/common";
import type { DbGeneration } from "@/types/database.types";
import type {
  ActivityPoint,
  BloomLevel,
  DistributionBucket,
  GeneratedQuestion,
  TopicCoverage,
} from "@/types/domain";

/** Number of items carried under `key` by a generation payload. */
function itemCount(g: DbGeneration, key: string): number {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  const items = payload[key];
  return Array.isArray(items) ? items.length : 0;
}

/** Question items across a generation (question_bank / test_help). */
function questionItems(g: DbGeneration): GeneratedQuestion[] {
  const payload = (g.payload ?? {}) as Record<string, unknown>;
  const questions = payload.questions;
  return Array.isArray(questions) ? (questions as GeneratedQuestion[]) : [];
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

const BLOOM_LEVELS: BloomLevel[] = [
  "Knowledge",
  "Understanding",
  "Application",
  "Analysis",
  "Evaluation",
  "Creation",
];

/** Bucket question items by a per-question field. */
function distribution(
  generations: DbGeneration[],
  pick: (q: GeneratedQuestion) => string | undefined,
): DistributionBucket[] {
  const counts = new Map<string, number>();
  for (const g of generations) {
    for (const q of questionItems(g)) {
      const key = pick(q);
      if (!key) continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

/** Bloom distribution includes every level so the taxonomy bar never empties. */
function bloomDistribution(generations: DbGeneration[]): DistributionBucket[] {
  const byLevel = new Map<string, number>();
  for (const g of generations) {
    for (const q of questionItems(g)) {
      if (q.bloom) byLevel.set(q.bloom, (byLevel.get(q.bloom) ?? 0) + 1);
    }
  }
  return BLOOM_LEVELS.map((level) => ({
    name: level,
    value: byLevel.get(level) ?? 0,
  }));
}

/** Question-type share rendered as a percentage on the pie legend. */
function typeDistribution(generations: DbGeneration[]): DistributionBucket[] {
  const counts = distribution(generations, (q) => q.type);
  const total = counts.reduce((n, c) => n + c.value, 0);
  if (total === 0) return [];
  return counts.map((c) => ({
    name: c.name,
    value: Math.round((c.value / total) * 1000) / 10,
  }));
}

/** ISO week (Monday-first) key for a timestamp. */
function weekKey(iso: string): string {
  const date = new Date(iso);
  const monday = new Date(date);
  monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return monday.toISOString().slice(0, 10);
}

const WEEKS = 6;

/** Last `WEEKS` weeks of generation volume + quality, oldest → newest. */
function activitySeries(generations: DbGeneration[]): ActivityPoint[] {
  const buckets = new Map<string, DbGeneration[]>();
  for (const g of generations) {
    const key = weekKey(g.created_at);
    const list = buckets.get(key) ?? [];
    list.push(g);
    buckets.set(key, list);
  }
  const latest = new Date(
    generations.length > 0 ? weekKey(generations[0].created_at) : weekKey(new Date().toISOString()),
  );
  latest.setDate(latest.getDate() - (WEEKS - 1) * 7);
  const weeks: string[] = [];
  for (let i = 0; i < WEEKS; i++) {
    const monday = new Date(latest);
    monday.setDate(latest.getDate() + i * 7);
    weeks.push(monday.toISOString().slice(0, 10));
  }
  return weeks.map((week) => {
    const bucket = buckets.get(week) ?? [];
    const quality = mean(bucket.map((g) => g.quality_score).filter((v): v is number => v != null));
    return {
      week: week.slice(5).replace("-", "/"),
      questions: bucket.reduce((n, g) => n + itemCount(g, "questions"), 0),
      flashcards: bucket.reduce((n, g) => n + itemCount(g, "flashcards"), 0),
      quality: quality != null ? Math.round(quality * 10) / 10 : 0,
    };
  });
}

export const AnalyticsService = {
  async get(query: AnalyticsQuery): Promise<Result<AnalyticsResponse>> {
    return attempt("AnalyticsService.get", async () => {
      if (isMockMode()) {
        const { getAnalytics } = await import("@/api/analytics.api");
        return getAnalytics(query);
      }
      // Real mode: every chart and stat is computed live from the site's
      // Supabase data (migration 019's staff read path) so the numbers always
      // reflect the real database. There is no FastAPI /analytics endpoint.
      const [generations, stats] = await Promise.all([
        supabaseApi.listAllGenerations(),
        adminApi.getAdminStats(),
      ]);
      const grounding = mean(
        generations.map((g) => g.grounding_score).filter((v): v is number => v != null),
      );
      const reviewed = generations.filter((g) => g.review_status !== "pending").length;
      const reviewCompletion =
        generations.length > 0 ? (reviewed / generations.length) * 100 : null;
      const summary: AnalyticsSummary = {
        questions: stats.questions,
        flashcards: stats.flashcards,
        studyPlans: stats.studyPlans,
        quality: stats.quality,
        grounding: grounding != null ? Math.round(grounding * 10) / 10 : null,
        reviewCompletion: reviewCompletion != null ? Math.round(reviewCompletion * 10) / 10 : null,
      };
      return {
        bloomDistribution: bloomDistribution(generations),
        typeDistribution: typeDistribution(generations),
        activitySeries: activitySeries(generations),
        topicCoverage: [] as TopicCoverage[],
        summary,
      };
    });
  },
};
