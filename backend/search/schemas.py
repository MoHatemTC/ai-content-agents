"""M4 search read-model schemas, matching the Sensei-AI TS contracts.

Shapes match ``Sensei-AI/src/types/api/catalogue.contracts.ts``
(``SearchQuery`` / ``SearchResponse``) and ``src/types/domain.ts``
(``SearchResult`` / ``SearchResultKind``). The backend only emits
``document``-kind results in M4 — the other kinds depend on their owning
milestones (M5 questions/flashcards, M6 chat history, M10 concepts) — so the
schema accepts the full kind union but the service never produces anything
but ``document``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SearchResultKind = Literal["document", "question", "flashcard", "concept", "history"]

# The only kind M4 retrieval can produce; other kinds return empty results.
SUPPORTED_SEARCH_KIND: SearchResultKind = "document"


class SearchResult(BaseModel):
    id: str
    kind: SearchResultKind
    title: str
    subtitle: str | None = None
    to: str


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0
