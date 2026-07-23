"""End-to-end pipeline test for the retrieval lane.

Exercises the full grounded-answer path against the *real* shared contracts,
fully offline: ingest documents into sessions, retrieve scoped top-k chunks,
render the actual mentor prompt template with the grounded ``{content}``
payload, build ``MentorOutput`` references that satisfy the
``ReferencesPresentRule`` guardrail, verify citation provenance, and wire
``AgentRun.source_chunk_ids``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from src.retrieval.config import RetrievalConfig
from src.retrieval.grounding import build_grounded_context, verify_references
from src.retrieval.index import ChunkIndex, HashingEmbeddingFunction, split_text_into_chunks
from src.retrieval.models import InsufficientGroundingError, RetrievalScope
from src.retrieval.retriever import ChromaRetriever
from src.validation.guardrails import GuardrailContext, ReferencesPresentRule
from src.validation.review_schema import AgentRun
from src.validation.schemas import ContentReference, MentorOutput

PHYSICS_TEXT = """Newton's second law states that force equals mass times acceleration.
In code form: `force = {mass} * {acceleration}` with placeholder braces.

Acceleration measures how quickly velocity changes over time."""

GIT_TEXT = """Git branches are lightweight pointers to commits.
Creating a branch does not copy the repository."""


@pytest.fixture()
def pipeline() -> tuple[ChunkIndex, ChromaRetriever]:
    """Two documents ingested into two different sessions, plus a retriever."""
    index = ChunkIndex(
        RetrievalConfig(collection_name=f"pipeline-{uuid4().hex}"),
        embedding_function=HashingEmbeddingFunction(),
    )
    physics_chunks = split_text_into_chunks(
        PHYSICS_TEXT, document_id="physics-notes", session_id="session-1"
    )
    git_chunks = split_text_into_chunks(GIT_TEXT, document_id="git-notes", session_id="session-2")
    index.add_document("physics-notes", physics_chunks)
    index.add_document("git-notes", git_chunks)
    return index, ChromaRetriever(index)


def load_mentor_template() -> str:
    """Load the real mentor prompt template shipped by the agents lane."""
    prompt_path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "mentor.yaml"
    data = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
    return str(data["prompt_template"])


class TestGroundedPipeline:
    def test_scoped_retrieval_returns_only_selected_session(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        context = build_grounded_context(
            "newton force acceleration", RetrievalScope(session_id="session-1"), retriever
        )
        assert context.is_sufficient
        assert all(chunk_id.startswith("physics-notes") for chunk_id in context.chunk_ids)
        # The other session's content is never part of the payload.
        assert not any("git" in chunk_id for chunk_id in context.chunk_ids)

    def test_grounded_content_fills_real_mentor_template(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        context = build_grounded_context(
            "newton force mass acceleration", RetrievalScope(document_id="physics-notes"), retriever
        )
        template = load_mentor_template()
        prompt = template.format(
            content=context.as_prompt_content(),
            user_question="What is Newton's second law?",
            difficulty="beginner",
        )
        # The rendered prompt carries the citation markers agents must echo.
        for chunk_id in context.chunk_ids:
            assert f"[{chunk_id}]" in prompt
        # Brace-bearing chunk text passes through str.format untouched:
        # substituted values are not re-processed as replacement fields.
        assert "`force = {mass} * {acceleration}`" in prompt

    def test_references_satisfy_grounding_guardrail(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        context = build_grounded_context(
            "newton force", RetrievalScope(document_id="physics-notes"), retriever
        )
        output = MentorOutput(
            explanation="Force equals mass times acceleration, per the provided notes.",
            key_points=["F = m * a"],
            next_steps=["Work through an example with real numbers."],
            references=context.to_content_references(),
        )
        assert ReferencesPresentRule().check(output, GuardrailContext()) is None

    def test_verify_references_round_trip_and_fabrication(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        context = build_grounded_context(
            "newton force", RetrievalScope(document_id="physics-notes"), retriever
        )
        good = verify_references(context.to_content_references(), context)
        assert good.valid is True

        fabricated = ContentReference(segment_id="git-notes-c0000", text="out of scope")
        bad = verify_references([fabricated], context)
        assert bad.valid is False
        assert bad.unknown_segment_ids == ["git-notes-c0000"]

    def test_agent_run_provenance_wiring(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        context = build_grounded_context(
            "newton force", RetrievalScope(document_id="physics-notes"), retriever
        )
        run = AgentRun(
            agent_name="mentor",
            input_context=context.as_prompt_content(),
            source_chunk_ids=context.chunk_ids,
            started_at=datetime.now(timezone.utc),
        )
        assert run.source_chunk_ids == context.chunk_ids
        assert run.input_context is not None
        assert context.chunk_ids[0] in run.input_context

    def test_out_of_scope_query_yields_insufficient_grounding(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        _, retriever = pipeline
        # git vocabulary, but scoped to the physics session: no grounding.
        context = build_grounded_context(
            "git branches pointers commits", RetrievalScope(session_id="session-1"), retriever
        )
        assert context.is_sufficient is False
        with pytest.raises(InsufficientGroundingError):
            context.as_prompt_content()

    def test_incremental_ingestion_is_immediately_retrievable(
        self, pipeline: tuple[ChunkIndex, ChromaRetriever]
    ) -> None:
        index, retriever = pipeline
        before = build_grounded_context(
            "chlorophyll photosynthesis", RetrievalScope(session_id="session-1"), retriever
        )
        assert before.is_sufficient is False

        new_chunks = split_text_into_chunks(
            "Chlorophyll absorbs light during photosynthesis.",
            document_id="bio-notes",
            session_id="session-1",
        )
        index.add_document("bio-notes", new_chunks)

        after = build_grounded_context(
            "chlorophyll photosynthesis", RetrievalScope(session_id="session-1"), retriever
        )
        assert after.is_sufficient
        assert after.chunk_ids == ["bio-notes-c0000"]