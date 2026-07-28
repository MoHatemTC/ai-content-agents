"""End-to-end pipeline tests: ingest -> retrieve -> agents -> validate -> review -> export.

Two layers here, deliberately separated:

* **Wiring tests** run offline against a stub agent. They prove the pipeline
  itself — that ingestion chunks reach the index, that provenance survives into
  the run record, and that a full review-and-export cycle works — without
  depending on a model being reachable.
* **Live tests** run the real agents against the real LiteLLM endpoint. They are
  the only way to learn anything true about groundedness, so they do not fall
  back to mocks: with no ``LITELLM_API_KEY`` configured they **skip**, because a
  green integration test that never called a model would be a lie.

Every Chroma index here gets a unique collection name — ``EphemeralClient`` is
shared per process, so same-named indexes see each other's chunks (see
``docs/retrieval-handoff.md`` section 5).
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from src.exports import ExportFormat, export_approved_run, export_outputs
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex
from src.retrieval.models import RetrievalScope
from src.validation.integration import Pipeline, to_retrieval_chunks
from src.validation.review_schema import ExportBlockedError, OutputStatus, RunStatus
from src.validation.review_service import ReviewService
from src.validation.schemas import ContentReference, MentorOutput

load_dotenv()

PHYSICS_NOTES = """
Newton's second law states that force equals mass times acceleration.

Acceleration measures how quickly velocity changes over time.

Momentum is the product of an object's mass and its velocity.
"""


def _index() -> ChunkIndex:
    """A Chroma index with a collection name unique to this test."""
    return ChunkIndex(RetrievalConfig(collection_name=f"test-{uuid4().hex}"))


class _StubAgent:
    """An agent that cites whatever it was actually given — the grounded ideal."""

    name = "mentor"
    schema = MentorOutput
    model = "stub-model"

    def __init__(self, cite: str | None = None) -> None:
        self.cite = cite
        self.seen_content: str | None = None

    def run_raw(self, content: str, **params: object) -> str:
        self.seen_content = content
        # Cite the first chunk id in the grounded content block, as a
        # well-behaved model would.
        segment_id = self.cite or content.split("]")[0].lstrip("[")
        return MentorOutput(
            explanation="Force equals mass times acceleration.",
            key_points=["F = ma"],
            next_steps=["Work through an example."],
            references=[ContentReference(segment_id=segment_id, text="excerpt")],
        ).model_dump_json()


@pytest.fixture()
def pipeline(tmp_path: Path) -> Pipeline:
    """A pipeline wired to a throwaway database, index and stub agent."""
    return Pipeline.build(
        db_path=str(tmp_path / "pipeline.db"),
        index=_index(),
        agents={"mentor": _StubAgent()},
    )


# --------------------------------------------------------------------------- #
# The ingestion -> retrieval bridge
# --------------------------------------------------------------------------- #


def test_bridge_renames_the_id_field_and_drops_offsets() -> None:
    from src.ingestion.schema import Chunk as IngestionChunk

    converted = to_retrieval_chunks(
        [
            IngestionChunk(
                id="doc-c0000",
                document_id="doc",
                text="some text",
                ordinal=0,
                start_char=0,
                end_char=9,
                session_id="session-1",
            )
        ]
    )

    assert len(converted) == 1
    assert converted[0].chunk_id == "doc-c0000"
    assert converted[0].session_id == "session-1"
    assert not hasattr(converted[0], "start_char")


def test_bridge_skips_blank_chunks_instead_of_failing() -> None:
    from src.ingestion.schema import Chunk as IngestionChunk

    converted = to_retrieval_chunks(
        [
            IngestionChunk(id="doc-c0000", document_id="doc", text="   ", ordinal=0),
            IngestionChunk(id="doc-c0001", document_id="doc", text="real", ordinal=1),
        ]
    )

    assert [chunk.chunk_id for chunk in converted] == ["doc-c0001"]


def test_ingested_material_becomes_retrievable(pipeline: Pipeline) -> None:
    document = pipeline.ingest_text(PHYSICS_NOTES, title="physics notes")

    context = pipeline.retrieve(
        "what is newton's second law", RetrievalScope(document_id=document.id)
    )

    assert context.is_sufficient
    assert all(chunk_id.startswith(document.id) for chunk_id in context.chunk_ids)
    assert "Newton" in context.as_prompt_content()


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #


def test_pipeline_records_provenance_end_to_end(pipeline: Pipeline) -> None:
    result = pipeline.ingest_and_run(
        PHYSICS_NOTES, "what is newton's second law", title="physics notes"
    )

    assert result.error is None
    assert result.grounded
    run = result.results[0].run
    assert run.status is RunStatus.SUCCESS
    assert run.source_chunk_ids == result.grounded_context.chunk_ids
    assert result.outputs[0].validation_passed is True


def test_agent_receives_the_grounded_content(tmp_path: Path) -> None:
    agent = _StubAgent()
    pipe = Pipeline.build(
        db_path=str(tmp_path / "p.db"), index=_index(), agents={"mentor": agent}
    )

    pipe.ingest_and_run(PHYSICS_NOTES, "what is momentum", title="physics notes")

    assert agent.seen_content is not None
    assert "Newton" in agent.seen_content or "Momentum" in agent.seen_content


def test_pipeline_refuses_to_run_agents_without_grounding(pipeline: Pipeline) -> None:
    """The core promise: no grounding, no generation."""
    pipeline.ingest_text(PHYSICS_NOTES, title="physics notes")

    result = pipeline.run(
        "a question about something else entirely",
        RetrievalScope(document_id="a-document-that-does-not-exist"),
    )

    assert result.error is not None
    assert result.results == []
    assert pipeline.platform_store.list_agent_runs() == []


def test_pipeline_flags_a_hallucinated_citation(tmp_path: Path) -> None:
    """A model citing an id it was never given is caught before review."""
    pipe = Pipeline.build(
        db_path=str(tmp_path / "p.db"),
        index=_index(),
        agents={"mentor": _StubAgent(cite="invented-chunk-id")},
    )

    result = pipe.ingest_and_run(PHYSICS_NOTES, "what is force", title="physics notes")

    output = result.outputs[0]
    assert output.validation_passed is False
    assert any(
        violation["rule_name"] == "grounded_references"
        for violation in output.validation_report["guardrail_violations"]
    )


def test_reingesting_a_document_does_not_duplicate_chunks(pipeline: Pipeline) -> None:
    document = pipeline.ingest_text(PHYSICS_NOTES, title="physics notes")
    before = len(pipeline.index)

    pipeline.ingest_text(PHYSICS_NOTES, title="physics notes")

    assert len(pipeline.index) == before
    assert pipeline.retrieve(
        "momentum", RetrievalScope(document_id=document.id)
    ).is_sufficient


# --------------------------------------------------------------------------- #
# The full scenario: generate -> review -> export
# --------------------------------------------------------------------------- #


def test_generated_output_cannot_be_exported_until_approved(
    pipeline: Pipeline,
) -> None:
    result = pipeline.ingest_and_run(
        PHYSICS_NOTES, "what is newton's second law", title="physics notes"
    )
    output = result.outputs[0]

    with pytest.raises(ExportBlockedError):
        export_outputs([output], ExportFormat.JSON)


def test_full_scenario_generate_review_export(pipeline: Pipeline) -> None:
    """The demo path, start to finish."""
    result = pipeline.ingest_and_run(
        PHYSICS_NOTES, "what is newton's second law", title="physics notes"
    )
    output = result.outputs[0]
    service = ReviewService(pipeline.platform_store)

    assert output.status is OutputStatus.PENDING

    service.edit(
        output.id,
        "nour",
        {
            **output.payload,
            "explanation": "Force equals mass times acceleration (reviewed).",
        },
    )
    service.approve(output.id, "nour", notes="grounded and accurate")

    reviewed = service.get(output.id)
    assert reviewed.status is OutputStatus.APPROVED

    document = export_approved_run(
        reviewed.agent_run_id, ExportFormat.MARKDOWN, pipeline.platform_store
    ).decode("utf-8")

    assert "reviewed" in document
    assert [r.action.value for r in service.history(output.id)] == ["edit", "approve"]


def test_rejected_output_never_reaches_an_export(pipeline: Pipeline) -> None:
    result = pipeline.ingest_and_run(
        PHYSICS_NOTES, "what is newton's second law", title="physics notes"
    )
    output = result.outputs[0]
    service = ReviewService(pipeline.platform_store)

    service.reject(output.id, "nour", notes="not useful")

    exported = export_approved_run(
        output.agent_run_id, ExportFormat.JSON, pipeline.platform_store
    )
    assert b'"count": 0' in exported


# --------------------------------------------------------------------------- #
# Live: the real agents against the real endpoint
# --------------------------------------------------------------------------- #

live = pytest.mark.skipif(
    not os.getenv("LITELLM_API_KEY"),
    reason="Live pipeline tests need LITELLM_API_KEY; set it in .env to run them.",
)


@live
def test_live_pipeline_produces_a_reviewable_output(tmp_path: Path) -> None:
    """The real thing: a real model, grounded, validated and queued for review.

    Deliberately asserts on the *platform's* behaviour rather than the model's
    wording: that a run and an output were recorded, and that whatever the model
    said was judged rather than trusted.
    """
    pipe = Pipeline.build(
        db_path=str(tmp_path / "live.db"),
        index=_index(),
        mock_mode=False,
        max_retries=1,
        retry_backoff=0.5,
    )

    result = pipe.ingest_and_run(
        PHYSICS_NOTES,
        "what is newton's second law",
        title="physics notes",
        agents=["mentor"],
    )

    assert result.grounded
    run = result.results[0].run
    assert run.finished_at is not None

    if run.status is RunStatus.FAILURE:
        pytest.skip(f"LiteLLM gateway unavailable: {run.error}")

    output = result.outputs[0]
    assert output.status is OutputStatus.PENDING  # nothing is trusted on arrival
    assert output.validation_report  # a verdict was recorded either way
    assert output.schema_name == "MentorOutput"


@live
def test_live_output_is_judged_against_its_grounding(tmp_path: Path) -> None:
    """Whatever the model cites, the platform checks it against what it was given."""
    pipe = Pipeline.build(
        db_path=str(tmp_path / "live.db"),
        index=_index(),
        mock_mode=False,
        max_retries=1,
        retry_backoff=0.5,
    )

    result = pipe.ingest_and_run(
        PHYSICS_NOTES, "what is momentum", title="physics notes", agents=["mentor"]
    )

    run = result.results[0].run
    if run.status is RunStatus.FAILURE:
        pytest.skip(f"LiteLLM gateway unavailable: {run.error}")

    output = result.outputs[0]
    report = output.validation_report
    cited = [
        reference["segment_id"]
        for reference in output.payload.get("references", [])
        if isinstance(reference, dict)
    ]

    if output.validation_passed:
        # A passing output must have cited only chunks it was actually given.
        assert set(cited) <= set(run.source_chunk_ids)
    else:
        # A failing one must say why, rather than failing silently.
        assert report["schema_errors"] or report["guardrail_violations"]
