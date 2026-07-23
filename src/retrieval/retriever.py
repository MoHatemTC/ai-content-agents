"""Top-k retrieval over the chunk index, scoped to a document/session.

Defines the :class:`Retriever` protocol — the swap point for alternative
backends (e.g. a lexical or remote-embedding retriever) — and its Chroma
implementation. Scope enforcement happens *inside* the vector store via
metadata filters applied before the similarity search, so out-of-scope
chunks are never candidates, never scored, and never returned.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from src.retrieval.config import RetrievalConfig
from src.retrieval.models import Chunk, RetrievedChunk

if TYPE_CHECKING:
    from src.retrieval.index import ChunkIndex
    from src.retrieval.models import RetrievalScope

logger = logging.getLogger(__name__)


class Retriever(Protocol):
    """Anything that returns top-k in-scope chunks for a query."""

    def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k chunks relevant to ``query`` within ``scope``."""
        ...


class ChromaRetriever:
    """Chroma-backed :class:`Retriever` implementation.

    Converts Chroma cosine distances to similarity scores
    (``score = 1 - distance``), drops results at or below
    ``config.min_score`` (so zero-similarity matches never surface), orders
    deterministically by ``(-score, ordinal, chunk_id)``, and truncates to
    ``top_k``.
    """

    def __init__(self, index: ChunkIndex, config: RetrievalConfig | None = None) -> None:
        """Create the retriever.

        Args:
            index: The chunk index to search.
            config: Tunables (``top_k`` default and ``min_score``); defaults
                to :class:`RetrievalConfig`.
        """
        self._index = index
        self._config = config or RetrievalConfig()

    def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve the top-k chunks for a query within the given scope.

        Args:
            query: The user's question or search text; blank queries yield
                no results.
            scope: The document/session selection to search within — chunks
                outside it are never candidates.
            top_k: Result-count override; defaults to ``config.top_k``.

        Returns:
            Ranked results (rank 1 = most relevant), possibly fewer than
            ``top_k`` after the ``min_score`` filter, or empty when nothing
            in scope scores above it. An empty result is a valid outcome —
            deciding whether that is *sufficient* grounding is the grounding
            layer's job.
        """
        limit = top_k if top_k is not None else self._config.top_k
        if limit < 1 or not query.strip():
            return []

        raw = self._index.query(query, scope, limit)
        chunk_ids: list[str] = raw["ids"][0]
        documents: list[str] = raw["documents"][0]
        metadatas: list[dict[str, object]] = raw["metadatas"][0]
        distances: list[float] = raw["distances"][0]

        scored: list[tuple[float, Chunk]] = []
        for chunk_id, text, metadata, distance in zip(chunk_ids, documents, metadatas, distances):
            score = 1.0 - float(distance)
            if score <= self._config.min_score:
                continue
            session_id = metadata.get("session_id")
            scored.append(
                (
                    score,
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=str(metadata["document_id"]),
                        session_id=str(session_id) if session_id is not None else None,
                        ordinal=int(metadata["ordinal"]),  # type: ignore[call-overload]
                        text=text,
                    ),
                )
            )

        scored.sort(key=lambda pair: (-pair[0], pair[1].ordinal, pair[1].chunk_id))
        results = [
            RetrievedChunk(chunk=chunk, score=score, rank=position)
            for position, (score, chunk) in enumerate(scored[:limit], start=1)
        ]
        logger.debug(
            "Query %r in scope %s returned %d result(s)",
            query,
            scope.to_where(),
            len(results),
        )
        return results
