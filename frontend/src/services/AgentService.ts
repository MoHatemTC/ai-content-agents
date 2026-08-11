/** Agent catalogue business logic. */
import * as catalogueApi from "@/api/catalogue.api";
import { attempt } from "@/lib/result";
import type { Result } from "@/types/api/common";
import type { Agent } from "@/types/domain";

export const AgentService = {
  async list(): Promise<Result<Agent[]>> {
    return attempt("AgentService.list", async () => (await catalogueApi.getAgents()).agents);
  },

  async get(slug: string): Promise<Result<Agent>> {
    return attempt("AgentService.get", async () => (await catalogueApi.getAgent(slug)).agent);
  },
};
