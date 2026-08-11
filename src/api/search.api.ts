/** Global search endpoint. */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import { documents, flashcards, history, questions } from "@/mock/mock-data";
import type { SearchQuery, SearchResponse } from "@/types/api/catalogue.contracts";
import type { SearchResult } from "@/types/domain";

const CONCEPTS = ["Iteration protocol", "Eigenvalues", "Process scheduling", "Monetary policy"];

function buildIndex(): SearchResult[] {
  return [
    ...documents.map<SearchResult>((d) => ({
      id: d.id,
      kind: "document",
      title: d.title,
      subtitle: `${d.kind} · ${d.pages} pages`,
      to: "/library",
    })),
    ...questions.map<SearchResult>((q) => ({
      id: q.id,
      kind: "question",
      title: q.prompt,
      subtitle: `${q.type} · ${q.difficulty}`,
      to: "/generate",
    })),
    ...flashcards.map<SearchResult>((f, i) => ({
      id: `card-${i}`,
      kind: "flashcard",
      title: f.front,
      subtitle: "Flashcard",
      to: "/agents",
    })),
    ...CONCEPTS.map<SearchResult>((c) => ({
      id: `concept-${c}`,
      kind: "concept",
      title: c,
      subtitle: "Concept",
      to: "/agents",
    })),
    ...history.map<SearchResult>((h) => ({
      id: h.id,
      kind: "history",
      title: `${h.id} · ${h.agent}`,
      subtitle: `${h.doc} · ${h.date}`,
      to: "/history",
    })),
  ];
}

/** GET /search?q=… */
export async function search(query: SearchQuery): Promise<SearchResponse> {
  if (!isMockMode()) {
    const params = new URLSearchParams({ q: query.q });
    if (query.workspaceId) params.set("workspace_id", query.workspaceId);
    if (query.limit) params.set("limit", String(query.limit));
    query.kinds?.forEach((k) => params.append("kinds", k));
    return http.get<SearchResponse>(`${paths.search}?${params.toString()}`);
  }

  await delay(240);
  const needle = query.q.trim().toLowerCase();
  const index = buildIndex().filter((r) => !query.kinds || query.kinds.includes(r.kind));
  const results = needle
    ? index.filter(
        (r) => r.title.toLowerCase().includes(needle) || r.subtitle?.toLowerCase().includes(needle),
      )
    : index;
  return { results: results.slice(0, query.limit ?? 40), total: results.length };
}
