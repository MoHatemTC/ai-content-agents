"""Unit tests for the retrieval lane (:mod:`src.retrieval`).

Covers the retrieval data models, configuration, text splitter, the
chroma-backed incremental index, and the scope-filtered top-k retriever.
All tests run fully offline: index tests inject the deterministic
:class:`HashingEmbeddingFunction` so no embedding model is ever downloaded.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.retrieval.config import RetrievalConfig
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    InsufficientGroundingError,
    RetrievalScope,
    RetrievedChunk,
)
from src.validation.schemas import ContentReference


def make_chunk(
    doc: str = "doc-a",
    ordinal: int = 0,
    text: str = "some text",
    session: str | None = "session-1",
) -> Chunk:
    """Build a valid Chunk with the deterministic id convention."""
    return Chunk(
        chunk_id=f"{doc}-c{ordinal:04d}",
        document_id=doc,
        session_id=session,
        ordinal=ordinal,
        text=text,
    )


def make_retrieved(
    rank: int,
    score: float = 0.9,
    doc: str = "doc-a",
    text: str = "some text",
) -> RetrievedChunk:
    """Build a RetrievedChunk whose ordinal follows its rank."""
    return RetrievedChunk(
        chunk=make_chunk(doc=doc, ordinal=rank - 1, text=text),
        score=score,
        rank=rank,
    )


class TestRetrievalConfig:
    def test_defaults(self) -> None:
        config = RetrievalConfig()
        assert config.top_k == 5
        assert config.min_score == 0.0
        assert config.chunk_size == 800
        assert config.chunk_overlap == 100
        assert config.collection_name == "content_chunks"
        assert config.persist_directory is None

    def test_rejects_non_positive_top_k(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalConfig(top_k=0)

    def test_rejects_overlap_not_smaller_than_chunk_size(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalConfig(chunk_size=100, chunk_overlap=100)


class TestChunkModel:
    def test_builds_with_expected_fields(self) -> None:
        chunk = make_chunk(doc="physics-notes", ordinal=3, text="F = m * a")
        assert chunk.chunk_id == "physics-notes-c0003"
        assert chunk.document_id == "physics-notes"
        assert chunk.session_id == "session-1"
        assert chunk.ordinal == 3
        assert chunk.text == "F = m * a"

    def test_session_id_is_optional(self) -> None:
        chunk = make_chunk(session=None)
        assert chunk.session_id is None

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValidationError):
            make_chunk(text="")

    def test_rejects_negative_ordinal(self) -> None:
        with pytest.raises(ValidationError):
            make_chunk(ordinal=-1)


class TestRetrievalScope:
    def test_requires_at_least_one_field(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalScope()

    def test_document_only_where(self) -> None:
        scope = RetrievalScope(document_id="doc-a")
        assert scope.to_where() == {"document_id": "doc-a"}

    def test_session_only_where(self) -> None:
        scope = RetrievalScope(session_id="session-1")
        assert scope.to_where() == {"session_id": "session-1"}

    def test_both_fields_where_uses_and(self) -> None:
        scope = RetrievalScope(document_id="doc-a", session_id="session-1")
        assert scope.to_where() == {
            "$and": [{"document_id": "doc-a"}, {"session_id": "session-1"}]
        }


class TestGroundedContext:
    def _context(self) -> GroundedContext:
        return GroundedContext(
            query="what is newton's second law",
            scope=RetrievalScope(document_id="doc-a"),
            chunks=[
                make_retrieved(rank=1, score=0.92, text="Force equals mass times acceleration."),
                make_retrieved(rank=2, score=0.71, text="Acceleration is change in velocity."),
            ],
        )

    def test_is_sufficient_when_chunks_present(self) -> None:
        assert self._context().is_sufficient is True

    def test_chunk_ids_follow_rank_order(self) -> None:
        assert self._context().chunk_ids == ["doc-a-c0000", "doc-a-c0001"]

    def test_to_content_references_returns_shared_contract_models(self) -> None:
        references = self._context().to_content_references()
        assert all(isinstance(ref, ContentReference) for ref in references)
        assert [ref.segment_id for ref in references] == ["doc-a-c0000", "doc-a-c0001"]
        assert references[0].text == "Force equals mass times acceleration."

    def test_as_prompt_content_includes_segment_markers_and_text(self) -> None:
        rendered = self._context().as_prompt_content()
        assert "[doc-a-c0000]" in rendered
        assert "[doc-a-c0001]" in rendered
        assert "Force equals mass times acceleration." in rendered

    def test_empty_context_is_insufficient(self) -> None:
        context = GroundedContext(
            query="unrelated",
            scope=RetrievalScope(document_id="doc-a"),
            chunks=[],
        )
        assert context.is_sufficient is False
        assert context.chunk_ids == []

    def test_as_prompt_content_raises_when_empty(self) -> None:
        context = GroundedContext(
            query="unrelated",
            scope=RetrievalScope(document_id="doc-a"),
            chunks=[],
        )
        with pytest.raises(InsufficientGroundingError):
            context.as_prompt_content()
