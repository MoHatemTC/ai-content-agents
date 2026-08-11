/** Pipeline stages + demo catalogue content (documents, history, flashcards). */
import * as catalogueApi from "@/api/catalogue.api";
import { attempt } from "@/lib/result";
import type { CatalogueResponse, ListPipelineStepsResponse } from "@/types/api/catalogue.contracts";
import type { Result } from "@/types/api/common";
import type { RagStage } from "@/types/domain";

export const ContentService = {
  async pipelineSteps(workspaceId?: string): Promise<Result<ListPipelineStepsResponse>> {
    return attempt("ContentService.pipelineSteps", () =>
      catalogueApi.getPipelineSteps(workspaceId),
    );
  },

  async ragStages(): Promise<Result<RagStage[]>> {
    return attempt(
      "ContentService.ragStages",
      async () => (await catalogueApi.getRagStages()).stages,
    );
  },

  async catalogue(): Promise<Result<CatalogueResponse>> {
    return attempt("ContentService.catalogue", () => catalogueApi.getCatalogue());
  },
};
