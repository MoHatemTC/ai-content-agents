"""Unit tests for the retrieval lane (:mod:`src.retrieval`).

Covers the retrieval data models, configuration, text splitter, the
chroma-backed incremental index, and the scope-filtered top-k retriever.
All tests run fully offline: index tests inject the deterministic
:class:`HashingEmbeddingFunction` so no embedding model is ever downloaded.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.retrieval.config import RetrievalConfig
from src.retrieval.index import (
    ChunkIndex,
    HashingEmbeddingFunction,
    split_text_into_chunks,
)
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    InsufficientGroundingError,
    RetrievalScope,
    RetrievedChunk,
)
from src.retrieval.grounding import build_grounded_context, verify_references
from src.retrieval.retriever import ChromaRetriever
from src.validation.schemas import ContentReference


def make_index(**config_overrides: object) -> ChunkIndex:
    """A fresh in-memory index with the deterministic offline embedder.

    Chroma's EphemeralClient shares one in-process instance, so each test
    gets a unique collection name to stay isolated.
    """
    config = RetrievalConfig(
        collection_name=f"test-{uuid4().hex}",  # type: ignore[arg-type]
        **config_overrides,  # type: ignore[arg-type]
    )
    return ChunkIndex(config, embedding_function=HashingEmbeddingFunction())


@pytest.fixture()
def index() -> ChunkIndex:
    """Per-test isolated in-memory index."""
    return make_index()


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


class TestSplitTextIntoChunks:
    def test_empty_text_returns_no_chunks(self) -> None:
        assert split_text_into_chunks("", document_id="doc") == []
        assert split_text_into_chunks("  \n\n   ", document_id="doc") == []

    def test_single_paragraph_becomes_one_chunk(self) -> None:
        chunks = split_text_into_chunks(
            "Newton's second law relates force and mass.",
            document_id="physics",
            session_id="session-1",
        )
        assert len(chunks) == 1
        assert chunks[0].chunk_id == "physics-c0000"
        assert chunks[0].document_id == "physics"
        assert chunks[0].session_id == "session-1"
        assert chunks[0].ordinal == 0
        assert chunks[0].text == "Newton's second law relates force and mass."

    def test_paragraphs_pack_up_to_chunk_size(self) -> None:
        config = RetrievalConfig(chunk_size=60, chunk_overlap=10)
        text = "First paragraph about forces.\n\nSecond paragraph about mass.\n\nThird one about acceleration."
        chunks = split_text_into_chunks(text, document_id="doc", config=config)
        assert len(chunks) > 1
        assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
        # No paragraph is torn apart: each chunk holds whole paragraphs.
        for chunk in chunks:
            for paragraph in chunk.text.split("\n\n"):
                assert paragraph in text

    def test_oversized_paragraph_is_window_split_with_overlap(self) -> None:
        config = RetrievalConfig(chunk_size=50, chunk_overlap=15)
        words = [f"word{i:02d}" for i in range(30)]
        text = " ".join(words)  # one long paragraph, no blank lines
        chunks = split_text_into_chunks(text, document_id="doc", config=config)
        assert len(chunks) > 1
        # Every word survives the split.
        joined = " ".join(chunk.text for chunk in chunks)
        for word in words:
            assert word in joined
        # Consecutive windows overlap: each next chunk starts with words
        # already present at the end of the previous chunk.
        for previous, current in zip(chunks, chunks[1:]):
            first_word = current.text.split()[0]
            assert first_word in previous.text.split()

    def test_document_id_is_sanitized_for_citation_safe_ids(self) -> None:
        chunks = split_text_into_chunks("Some content.", document_id="My Notes! (v2)")
        assert len(chunks) == 1
        assert chunks[0].document_id == "My-Notes---v2-"
        assert chunks[0].chunk_id == "My-Notes---v2--c0000"


class TestHashingEmbeddingFunction:
    def test_is_deterministic_across_instances(self) -> None:
        first = HashingEmbeddingFunction()(["newton force mass"])
        second = HashingEmbeddingFunction()(["newton force mass"])
        assert first[0] == pytest.approx(second[0])

    def test_shared_vocabulary_scores_higher_cosine(self) -> None:
        embedder = HashingEmbeddingFunction()
        query, related, unrelated = embedder(
            [
                "newton force acceleration",
                "newton said force equals mass times acceleration",
                "git branches are lightweight pointers to commits",
            ]
        )

        def cosine(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalized

        assert cosine(query, related) > cosine(query, unrelated)


class TestChunkIndex:
    def test_default_embedder_is_offline_under_mock_mode(self) -> None:
        # conftest pins MOCK_MODE=true, so the default construction path must
        # pick the hashing embedder and never download an embedding model.
        default_index = ChunkIndex(RetrievalConfig(collection_name=f"test-{uuid4().hex}"))
        default_index.add_chunks([make_chunk()])
        assert len(default_index) == 1

    def test_starts_empty(self, index: ChunkIndex) -> None:
        assert len(index) == 0
        assert index.document_ids() == []

    def test_add_chunks_and_get_roundtrip(self, index: ChunkIndex) -> None:
        chunk = make_chunk(doc="doc-a", ordinal=0, text="Force equals mass times acceleration.")
        assert index.add_chunks([chunk]) == 1
        assert len(index) == 1
        fetched = index.get_chunk("doc-a-c0000")
        assert fetched == chunk

    def test_get_chunk_roundtrips_none_session(self, index: ChunkIndex) -> None:
        chunk = make_chunk(doc="doc-b", ordinal=0, session=None)
        index.add_chunks([chunk])
        fetched = index.get_chunk("doc-b-c0000")
        assert fetched is not None
        assert fetched.session_id is None

    def test_get_chunk_missing_returns_none(self, index: ChunkIndex) -> None:
        assert index.get_chunk("nope-c0000") is None

    def test_document_ids_lists_ingested_documents(self, index: ChunkIndex) -> None:
        index.add_chunks([make_chunk(doc="doc-a"), make_chunk(doc="doc-b")])
        assert index.document_ids() == ["doc-a", "doc-b"]

    def test_incremental_add_extends_existing_index(self, index: ChunkIndex) -> None:
        index.add_chunks([make_chunk(doc="doc-a", ordinal=0)])
        index.add_chunks([make_chunk(doc="doc-a", ordinal=1), make_chunk(doc="doc-b")])
        assert len(index) == 3

    def test_add_document_replaces_previous_version(self, index: ChunkIndex) -> None:
        old = split_text_into_chunks(
            "One.\n\nTwo.\n\nThree.",
            document_id="notes",
            config=RetrievalConfig(chunk_size=5, chunk_overlap=1),
        )
        assert index.add_document("notes", old) == 3
        new = split_text_into_chunks("Only paragraph now.", document_id="notes")
        assert index.add_document("notes", new) == 1
        assert len(index) == 1
        assert index.get_chunk("notes-c0001") is None
        assert index.get_chunk("notes-c0000") is not None

    def test_add_document_rejects_foreign_chunks(self, index: ChunkIndex) -> None:
        with pytest.raises(ValueError, match="does not belong"):
            index.add_document("notes", [make_chunk(doc="other")])

    def test_remove_document(self, index: ChunkIndex) -> None:
        index.add_chunks([make_chunk(doc="doc-a"), make_chunk(doc="doc-b")])
        assert index.remove_document("doc-a") == 1
        assert len(index) == 1
        assert index.get_chunk("doc-a-c0000") is None
        assert index.remove_document("doc-a") == 0


GIT_TEXT = "Git branches are lightweight pointers to commits in the repository."
PHOTO_TEXT = "Photosynthesis converts light energy into chemical energy in plants."
PHOTO_MORE = "Chlorophyll absorbs light energy during photosynthesis in leaves."


def seeded_retriever() -> tuple[ChunkIndex, ChromaRetriever]:
    """Index with two documents in two sessions, plus a retriever."""
    index = make_index()
    index.add_chunks(
        [
            Chunk(
                chunk_id="git-notes-c0000",
                document_id="git-notes",
                session_id="session-1",
                ordinal=0,
                text=GIT_TEXT,
            ),
            Chunk(
                chunk_id="bio-notes-c0000",
                document_id="bio-notes",
                session_id="session-2",
                ordinal=0,
                text=PHOTO_TEXT,
            ),
            Chunk(
                chunk_id="bio-notes-c0001",
                document_id="bio-notes",
                session_id="session-2",
                ordinal=1,
                text=PHOTO_MORE,
            ),
        ]
    )
    return index, ChromaRetriever(index)


class TestChromaRetriever:
    def test_relevant_chunk_ranks_first_with_descending_scores(self) -> None:
        _, retriever = seeded_retriever()
        results = retriever.retrieve(
            "photosynthesis light energy", RetrievalScope(session_id="session-2")
        )
        assert results
        assert results[0].chunk.chunk_id == "bio-notes-c0000"
        scores = [result.score for result in results]
        assert scores == sorted(scores, reverse=True)
        assert [result.rank for result in results] == list(range(1, len(results) + 1))

    def test_document_scope_never_leaks_other_documents(self) -> None:
        _, retriever = seeded_retriever()
        # Query matches only bio-notes vocabulary; scoping to git-notes must
        # return nothing rather than leak bio-notes chunks.
        assert retriever.retrieve(
            "photosynthesis chlorophyll light", RetrievalScope(document_id="git-notes")
        ) == []
        in_scope = retriever.retrieve(
            "photosynthesis chlorophyll light", RetrievalScope(document_id="bio-notes")
        )
        assert in_scope
        assert all(result.chunk.document_id == "bio-notes" for result in in_scope)

    def test_session_scope_never_leaks_other_sessions(self) -> None:
        _, retriever = seeded_retriever()
        assert retriever.retrieve(
            "photosynthesis light", RetrievalScope(session_id="session-1")
        ) == []
        in_scope = retriever.retrieve(
            "photosynthesis light", RetrievalScope(session_id="session-2")
        )
        assert in_scope
        assert all(result.chunk.session_id == "session-2" for result in in_scope)

    def test_document_and_session_scope_intersect(self) -> None:
        _, retriever = seeded_retriever()
        # bio-notes lives in session-2; pinning it to session-1 matches nothing.
        assert retriever.retrieve(
            "photosynthesis light",
            RetrievalScope(document_id="bio-notes", session_id="session-1"),
        ) == []

    def test_top_k_truncates_results(self) -> None:
        _, retriever = seeded_retriever()
        results = retriever.retrieve(
            "photosynthesis light", RetrievalScope(session_id="session-2"), top_k=1
        )
        assert len(results) == 1
        assert results[0].rank == 1

    def test_top_k_defaults_from_config(self) -> None:
        index = make_index()
        index.add_chunks(
            [make_chunk(doc="doc", ordinal=i, text=f"repeated term alpha {i}") for i in range(4)]
        )
        retriever = ChromaRetriever(index, RetrievalConfig(top_k=2))
        results = retriever.retrieve("alpha term", RetrievalScope(document_id="doc"))
        assert len(results) == 2

    def test_blank_query_returns_empty(self) -> None:
        _, retriever = seeded_retriever()
        assert retriever.retrieve("", RetrievalScope(document_id="bio-notes")) == []
        assert retriever.retrieve("   ", RetrievalScope(document_id="bio-notes")) == []

    def test_empty_index_returns_empty(self) -> None:
        retriever = ChromaRetriever(make_index())
        assert retriever.retrieve("anything", RetrievalScope(document_id="doc")) == []

    def test_min_score_filters_weak_matches(self) -> None:
        index = make_index()
        index.add_chunks([make_chunk(doc="doc", text="completely unrelated words here")])
        strict = ChromaRetriever(index, RetrievalConfig(min_score=0.99))
        assert strict.retrieve("photosynthesis light", RetrievalScope(document_id="doc")) == []

    def test_tie_break_is_deterministic_by_ordinal(self) -> None:
        index = make_index()
        same_text = "identical chunk text for tie breaking"
        index.add_chunks(
            [
                make_chunk(doc="doc", ordinal=1, text=same_text),
                make_chunk(doc="doc", ordinal=0, text=same_text),
            ]
        )
        retriever = ChromaRetriever(index)
        results = retriever.retrieve("identical chunk text", RetrievalScope(document_id="doc"))
        assert [result.chunk.chunk_id for result in results] == ["doc-c0000", "doc-c0001"]


class TestGroundingContract:
    def test_build_grounded_context_returns_in_scope_payload(self) -> None:
        _, retriever = seeded_retriever()
        scope = RetrievalScope(session_id="session-2")
        context = build_grounded_context("photosynthesis light energy", scope, retriever)
        assert context.query == "photosynthesis light energy"
        assert context.scope == scope
        assert context.is_sufficient
        assert all(chunk_id.startswith("bio-notes") for chunk_id in context.chunk_ids)

    def test_build_grounded_context_respects_top_k(self) -> None:
        _, retriever = seeded_retriever()
        context = build_grounded_context(
            "photosynthesis light", RetrievalScope(session_id="session-2"), retriever, top_k=1
        )
        assert len(context.chunks) == 1

    def test_build_grounded_context_insufficient_when_nothing_matches(self) -> None:
        _, retriever = seeded_retriever()
        context = build_grounded_context(
            "photosynthesis light", RetrievalScope(session_id="session-1"), retriever
        )
        assert context.is_sufficient is False
        with pytest.raises(InsufficientGroundingError):
            context.as_prompt_content()

    def test_verify_references_accepts_cited_subset(self) -> None:
        _, retriever = seeded_retriever()
        context = build_grounded_context(
            "photosynthesis light", RetrievalScope(session_id="session-2"), retriever
        )
        references = context.to_content_references()[:1]
        verification = verify_references(references, context)
        assert verification.valid is True
        assert verification.unknown_segment_ids == []

    def test_verify_references_flags_fabricated_segment_ids(self) -> None:
        _, retriever = seeded_retriever()
        context = build_grounded_context(
            "photosynthesis light", RetrievalScope(session_id="session-2"), retriever
        )
        fabricated = ContentReference(segment_id="made-up-c9999", text="invented")
        verification = verify_references(
            [*context.to_content_references(), fabricated], context
        )
        assert verification.valid is False
        assert verification.unknown_segment_ids == ["made-up-c9999"]
