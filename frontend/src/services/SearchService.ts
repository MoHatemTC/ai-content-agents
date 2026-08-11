/** Global search business logic — the only search entry point for the UI. */
import * as searchApi from "@/api/search.api";
import { attempt } from "@/lib/result";
import type { SearchQuery, SearchResponse } from "@/types/api/catalogue.contracts";
import type { Result } from "@/types/api/common";

export const SearchService = {
  async search(query: SearchQuery): Promise<Result<SearchResponse>> {
    return attempt("SearchService.search", () => searchApi.search(query));
  },
};
