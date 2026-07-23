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
from src.retrieval.index import (
    ChunkIndex,
    HashingEmbeddingFunction,
    sanitize_document_id,
    split_text_into_chunks,
)
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    InsufficientGroundingError,
    RetrievalScope,
    RetrievedChunk,
)
from src.retrieval.retriever import ChromaRetriever, Retriever

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
