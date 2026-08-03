"""Retrieval / grounding lane: scoped top-k retrieval with provenance.

Public API for other lanes:

- Ingest: :func:`split_text_into_chunks` -> :meth:`ChunkIndex.add_document`
- Retrieve: :class:`ChromaRetriever` (or any :class:`Retriever`)
- Ground: :func:`build_grounded_context` -> :class:`GroundedContext`
- Verify: :func:`verify_references`

See ``docs/retrieval-lane.md`` for the full contract.
"""

from src.retrieval.config import RetrievalConfig
from src.retrieval.grounding import (
    GroundingVerification,
    build_grounded_context,
    verify_references,
)
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    InsufficientGroundingError,
    RetrievalScope,
    RetrievedChunk,
)
from src.retrieval.retriever import ChromaRetriever, Retriever

try:
    from src.retrieval.index import (
        ChunkIndex,
        HashingEmbeddingFunction,
        sanitize_document_id,
        split_text_into_chunks,
    )
except ModuleNotFoundError:
    ChunkIndex = None  # type: ignore[assignment]
    HashingEmbeddingFunction = None  # type: ignore[assignment]

    def sanitize_document_id(document_id: str) -> str:  # type: ignore[override]
        raise ModuleNotFoundError(
            "chromadb is required for sanitize_document_id; install chromadb or avoid retrieval indexing."
        )

    def split_text_into_chunks(*args, **kwargs):  # type: ignore[override]
        raise ModuleNotFoundError(
            "chromadb is required for split_text_into_chunks; install chromadb or avoid retrieval indexing."
        )

__all__ = [
    "Chunk",
    "ChunkIndex",
    "ChromaRetriever",
    "GroundedContext",
    "GroundingVerification",
    "HashingEmbeddingFunction",
    "InsufficientGroundingError",
    "RetrievalConfig",
    "RetrievalScope",
    "RetrievedChunk",
    "Retriever",
    "build_grounded_context",
    "sanitize_document_id",
    "split_text_into_chunks",
    "verify_references",
]
