"""Configuration for the retrieval lane.

A single :class:`RetrievalConfig` object carries every tunable the lane
exposes so callers (tests, services, future UI) configure retrieval in one
place instead of scattering constants.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RetrievalConfig(BaseModel):
    """Tunables for chunking, indexing, and top-k retrieval.

    Attributes:
        top_k: Default number of chunks returned by a retrieval call.
        min_score: Cosine-similarity floor; results scoring below it are
            dropped. The default ``0.0`` keeps every non-negative match.
        chunk_size: Target chunk length in characters for the text splitter.
        chunk_overlap: Character overlap between windows when a single
            oversized paragraph must be split. Must be smaller than
            ``chunk_size``.
        collection_name: Name of the backing Chroma collection.
        persist_directory: When set, the index persists on disk at this path
            (Chroma ``PersistentClient``); when ``None`` the index lives
            in memory only (``EphemeralClient``).
    """

    top_k: int = Field(default=5, ge=1)
    min_score: float = Field(default=0.0)
    chunk_size: int = Field(default=800, ge=1)
    chunk_overlap: int = Field(default=100, ge=0)
    collection_name: str = Field(default="content_chunks", min_length=1)
    persist_directory: str | None = None

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk_size(self) -> RetrievalConfig:
        """Reject overlaps that would make the splitter loop forever."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self
