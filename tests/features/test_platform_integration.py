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
shared per process, so same-named indexes would see each other's chunks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from src.exports import ExportFormat, export_approved_run, export_outputs
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex
from src.retrieval.models import RetrievalScope
from src.validation.automation import DEMO_DATASET, load_dataset, run_batch
from src.validation.automation import main as automation_main
from src.validation.history import BATCH_COMPLETED, BATCH_STARTED
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
        violation["rule_name"] == "grounding_verification"
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
# Batch automation
# --------------------------------------------------------------------------- #


def _batch_pipeline(tmp_path: Path, agent: object | None = None) -> Pipeline:
    """A pipeline for batch tests, wired to a stub agent."""
    return Pipeline.build(
        db_path=str(tmp_path / "batch.db"),
        index=_index(),
        agents={"mentor": agent or _StubAgent()},
    )


def test_batch_processes_every_document(tmp_path: Path) -> None:
    pipe = _batch_pipeline(tmp_path)

    report = run_batch(DEMO_DATASET, pipeline=pipe, limit=2)

    assert len(report.items) == 2
    assert report.failed_items == []
    assert len(report.output_ids) == 2
    assert report.elapsed_seconds >= 0


def test_batch_leaves_everything_pending_review(tmp_path: Path) -> None:
    """A batch must never bypass the gate by approving its own work."""
    pipe = _batch_pipeline(tmp_path)

    run_batch(DEMO_DATASET, pipeline=pipe, limit=2)

    outputs = pipe.platform_store.list_outputs()
    assert outputs
    assert all(output.status is OutputStatus.PENDING for output in outputs)
    assert pipe.platform_store.list_reviews() == []


def test_batch_scores_only_its_own_runs(tmp_path: Path) -> None:
    pipe = _batch_pipeline(tmp_path)
    pipe.ingest_and_run(PHYSICS_NOTES, "what is force", title="earlier work")

    report = run_batch(DEMO_DATASET, pipeline=pipe, limit=1)

    assert report.evaluation is not None
    assert report.evaluation.overall.outputs == 1


def test_one_failing_document_does_not_stop_the_batch(tmp_path: Path) -> None:
    class _Exploding:
        name, schema, model = "mentor", MentorOutput, "stub"

        def __init__(self) -> None:
            self.calls = 0

        def run_raw(self, content: str, **params: object) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("upstream is down")
            return _StubAgent().run_raw(content, **params)

    pipe = Pipeline.build(
        db_path=str(tmp_path / "batch.db"),
        index=_index(),
        agents={"mentor": _Exploding()},
        max_retries=0,
    )

    report = run_batch(DEMO_DATASET, pipeline=pipe, limit=2)

    assert len(report.items) == 2
    assert len(report.output_ids) == 1  # the second document still ran


def test_batch_report_renders_readably(tmp_path: Path) -> None:
    report = run_batch(DEMO_DATASET, pipeline=_batch_pipeline(tmp_path), limit=1)

    rendered = report.render()

    assert "Batch run" in rendered
    assert "pending human review" in rendered
    assert "Evaluation" in rendered


def test_batch_logs_its_start_and_finish(tmp_path: Path) -> None:
    pipe = _batch_pipeline(tmp_path)

    run_batch(DEMO_DATASET, pipeline=pipe, limit=1)

    logged = {event.event_type for event in pipe.platform_store.list_events()}
    assert {BATCH_STARTED, BATCH_COMPLETED} <= logged


def test_dataset_can_be_loaded_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps([{"title": "t", "text": "some material", "query": "a question"}]),
        encoding="utf-8",
    )

    dataset = load_dataset(path)

    assert len(dataset) == 1
    assert dataset[0].query == "a question"


def test_malformed_dataset_is_rejected_clearly(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([{"title": "missing the rest"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="title"):
        load_dataset(path)


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


@live
def test_cli_reports_success_for_a_clean_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI entry point runs a batch end to end and reports success.

    Live because it has to be: the ``--offline`` flag it used to pass is
    gone with mock mode, and the CLI builds its own pipeline, so there is
    no seam to inject a fake client through. The batch logic itself stays
    covered offline by the ``run_batch(pipeline=...)`` tests above; what is
    only exercised here is argument parsing through to a real run.
    """
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            [{"title": "Physics", "text": PHYSICS_NOTES, "query": "what is force"}]
        ),
        encoding="utf-8",
    )

    exit_code = automation_main(
        [
            "--dataset",
            str(dataset),
            "--db",
            str(tmp_path / "cli.db"),
            "--agents",
            "mentor",
        ]
    )

    assert exit_code == 0
    assert "Batch run" in capsys.readouterr().out
