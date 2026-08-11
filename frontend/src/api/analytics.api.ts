/** Analytics endpoints. */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import {
  activitySeries,
  analyticsSummary,
  bloomDistribution,
  topicCoverage,
  typeDistribution,
} from "@/mock/mock-data";
import type { AnalyticsQuery, AnalyticsResponse } from "@/types/api/analytics.contracts";

export async function getAnalytics(query: AnalyticsQuery): Promise<AnalyticsResponse> {
  if (!isMockMode()) {
    return http.get<AnalyticsResponse>(
      `${paths.analytics}?workspace_id=${query.workspaceId}&range=${query.range ?? "30d"}`,
    );
  }
  await delay(80);
  return {
    bloomDistribution,
    typeDistribution,
    activitySeries,
    topicCoverage,
    summary: analyticsSummary,
  };
}
