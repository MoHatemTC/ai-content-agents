/** Model catalogue business logic. */
import * as modelApi from "@/api/model.api";
import type { ModelInfo } from "@/types/api/analytics.contracts";

export const ModelService = {
  list(): ModelInfo[] {
    return modelApi.AVAILABLE_MODELS;
  },
  fetch: modelApi.getModels,
  defaultModelId: modelApi.getDefaultModelId,
};
