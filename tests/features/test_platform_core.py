"""Offline tests for the platform core: lifecycle, store, guardrails, export, evaluation.

Everything here is pure logic over in-memory models and temporary SQLite files —
no agent, no network, no Streamlit. The live end-to-end path is covered separately
in ``tests/features/test_platform_integration.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.guardrails import (
    GroundedReferencesRule,
    GuardrailContext,
    ReferencesPresentRule,
    Severity,
)
from src.validation.review_schema import (
    AgentRun,
    GeneratedOutput,
    IllegalTransitionError,
    OutputStatus,
    Review,
    ReviewAction,
    RunStatus,
    SystemEvent,
    apply_review,
    assert_exportable,
    is_legal_transition,
)
from src.validation.schemas import (
    ContentReference,
    DifficultyLevel,
    MentorOutput,
    QuestionBankOutput,
    QuestionItem,
    QuestionType,
)
from src.validation.store import PlatformStore
from src.validation.validator_base import ValidatorBase


def _make_output(status: OutputStatus = OutputStatus.PENDING) -> GeneratedOutput:
    """Build a GeneratedOutput in a given status for lifecycle/gate tests."""
    run = AgentRun(agent_name="demo-agent")
    return GeneratedOutput(
        agent_run_id=run.id,
        output_type="demo",
        payload={"question": "q", "answer": "a", "references": ["chunk-1"]},
        schema_name="DemoItem",
        status=status,
    )


@pytest.fixture()
def store(tmp_path: Path) -> PlatformStore:
    """A PlatformStore backed by a throwaway database file."""
    return PlatformStore(db_path=str(tmp_path / "platform.db"))


# --------------------------------------------------------------------------- #
# Reject action (Week 3 extension of the Sprint 1 lifecycle)
# --------------------------------------------------------------------------- #


def test_reject_is_reachable_from_pending_and_edited() -> None:
    assert is_legal_transition(OutputStatus.PENDING, OutputStatus.REJECTED)
    assert is_legal_transition(OutputStatus.EDITED, OutputStatus.REJECTED)


def test_rejected_is_terminal() -> None:
    assert not is_legal_transition(OutputStatus.REJECTED, OutputStatus.PENDING)
    assert not is_legal_transition(OutputStatus.REJECTED, OutputStatus.EDITED)
    assert not is_legal_transition(OutputStatus.REJECTED, OutputStatus.APPROVED)


def test_reject_pending_output() -> None:
    output = _make_output()

    review = apply_review(output, "nour", ReviewAction.REJECT, notes="off topic")

    assert output.status is OutputStatus.REJECTED
    assert review.previous_status is OutputStatus.PENDING
    assert review.new_status is OutputStatus.REJECTED
    assert review.notes == "off topic"


def test_reject_edited_output() -> None:
    output = _make_output()
    apply_review(output, "nour", ReviewAction.EDIT, edited_payload={"a": 1})

    apply_review(output, "nour", ReviewAction.REJECT)

    assert output.status is OutputStatus.REJECTED


@pytest.mark.parametrize(
    "action",
    [ReviewAction.APPROVE, ReviewAction.EDIT, ReviewAction.REJECT],
)
def test_no_status_change_out_of_rejected(action: ReviewAction) -> None:
    output = _make_output(OutputStatus.REJECTED)

    with pytest.raises(IllegalTransitionError):
        apply_review(output, "nour", action, edited_payload={"a": 1})

    assert output.status is OutputStatus.REJECTED


def test_comment_still_allowed_on_rejected_output() -> None:
    """Rejected is terminal for status, but the audit trail stays open."""
    output = _make_output(OutputStatus.REJECTED)

    review = apply_review(output, "nour", ReviewAction.COMMENT, notes="agreed")

    assert output.status is OutputStatus.REJECTED
    assert review.previous_status is review.new_status is OutputStatus.REJECTED


def test_approve_after_reject_is_blocked() -> None:
    """The gate's whole point: a rejected output can never become exportable."""
    output = _make_output()
    apply_review(output, "nour", ReviewAction.REJECT)

    with pytest.raises(IllegalTransitionError):
        apply_review(output, "someone-else", ReviewAction.APPROVE)


def test_rejected_output_is_not_exportable() -> None:
    from src.validation.review_schema import ExportBlockedError

    with pytest.raises(ExportBlockedError):
        assert_exportable(_make_output(OutputStatus.REJECTED))


# --------------------------------------------------------------------------- #
# PlatformStore: persistence for agent_runs / generated_outputs / reviews
# --------------------------------------------------------------------------- #


def test_agent_run_round_trip(store: PlatformStore) -> None:
    run = AgentRun(
        agent_name="mentor",
        input_context="[doc-c0000] Newton's second law...",
        source_chunk_ids=["doc-c0000", "doc-c0001"],
        model="kimi-k2.6",
    )

    store.save_agent_run(run)
    loaded = store.get_agent_run(run.id)

    assert loaded is not None
    assert loaded.agent_name == "mentor"
    assert loaded.source_chunk_ids == ["doc-c0000", "doc-c0001"]
    assert loaded.status is RunStatus.SUCCESS
    assert loaded.started_at == run.started_at


def test_saving_a_run_twice_updates_it(store: PlatformStore) -> None:
    """A run is written when it starts and rewritten when it finishes."""
    run = AgentRun(agent_name="mentor")
    store.save_agent_run(run)

    run.status = RunStatus.FAILURE
    run.error = "AzureException APIConnectionError"
    store.save_agent_run(run)

    loaded = store.get_agent_run(run.id)
    assert loaded is not None
    assert loaded.status is RunStatus.FAILURE
    assert loaded.error == "AzureException APIConnectionError"
    assert len(store.list_agent_runs()) == 1


def test_generated_output_round_trip_preserves_verdict(store: PlatformStore) -> None:
    run = AgentRun(agent_name="mentor")
    store.save_agent_run(run)
    output = GeneratedOutput(
        agent_run_id=run.id,
        output_type="mentor",
        payload={"explanation": "...", "references": [{"segment_id": "doc-c0000"}]},
        schema_name="MentorOutput",
        validation_passed=False,
        validation_report={"passed": False, "schema_errors": ["boom"]},
    )

    store.save_output(output)
    loaded = store.get_output(output.id)

    assert loaded is not None
    assert loaded.payload == output.payload
    assert loaded.validation_passed is False
    assert loaded.validation_report == {"passed": False, "schema_errors": ["boom"]}
    assert loaded.status is OutputStatus.PENDING


def test_list_outputs_filters_by_status_and_run(store: PlatformStore) -> None:
    run_a, run_b = AgentRun(agent_name="mentor"), AgentRun(agent_name="concept")
    store.save_agent_run(run_a)
    store.save_agent_run(run_b)
    for run, status in [
        (run_a, OutputStatus.PENDING),
        (run_a, OutputStatus.APPROVED),
        (run_b, OutputStatus.PENDING),
    ]:
        store.save_output(
            GeneratedOutput(
                agent_run_id=run.id,
                output_type="demo",
                payload={},
                schema_name="DemoItem",
                status=status,
            )
        )

    assert len(store.list_outputs()) == 3
    assert len(store.list_outputs(status=OutputStatus.PENDING)) == 2
    assert len(store.list_outputs(agent_run_id=run_a.id)) == 2
    assert len(store.list_outputs(agent_name="concept")) == 1
    assert (
        len(store.list_outputs(agent_run_id=run_a.id, status=OutputStatus.APPROVED))
        == 1
    )


def test_reviews_are_append_only(store: PlatformStore) -> None:
    """The audit trail can only grow — the store exposes no update or delete."""
    output = _make_output()
    store.save_output(output)

    first = apply_review(output, "nour", ReviewAction.EDIT, edited_payload={"a": 1})
    store.save_review(first)
    second = apply_review(output, "nour", ReviewAction.APPROVE)
    store.save_review(second)

    assert not hasattr(store, "update_review")
    assert not hasattr(store, "delete_review")

    history = store.list_reviews(output_id=output.id)
    assert [r.action for r in history] == [ReviewAction.EDIT, ReviewAction.APPROVE]
    assert [r.new_status for r in history] == [
        OutputStatus.EDITED,
        OutputStatus.APPROVED,
    ]
    assert history[0].edited_payload == {"a": 1}


def test_review_history_is_scoped_to_its_output(store: PlatformStore) -> None:
    one, two = _make_output(), _make_output()
    store.save_output(one)
    store.save_output(two)
    store.save_review(apply_review(one, "nour", ReviewAction.APPROVE))
    store.save_review(apply_review(two, "nour", ReviewAction.REJECT))

    assert [r.action for r in store.list_reviews(output_id=one.id)] == [
        ReviewAction.APPROVE
    ]
    assert len(store.list_reviews()) == 2


def test_status_change_is_persisted(store: PlatformStore) -> None:
    output = _make_output()
    store.save_output(output)

    apply_review(output, "nour", ReviewAction.APPROVE)
    store.save_output(output)

    reloaded = store.get_output(output.id)
    assert reloaded is not None
    assert reloaded.status is OutputStatus.APPROVED


def test_missing_records_return_none(store: PlatformStore) -> None:
    assert store.get_output("nope") is None
    assert store.get_agent_run("nope") is None


def test_events_are_logged_and_queryable(store: PlatformStore) -> None:
    store.log_event("run_started", "mentor run started", run_id="run-1")
    store.log_event("export_blocked", "blocked", output_id="out-1", details={"n": 2})

    assert len(store.list_events()) == 2
    blocked = store.list_events(event_type="export_blocked")
    assert len(blocked) == 1
    assert isinstance(blocked[0], SystemEvent)
    assert blocked[0].details == {"n": 2}
    assert len(store.list_events(run_id="run-1")) == 1


def test_store_reopens_an_existing_database(tmp_path: Path) -> None:
    """State survives the process — the Streamlit page and the CLI share a file."""
    db = str(tmp_path / "platform.db")
    output = _make_output()
    PlatformStore(db_path=db).save_output(output)

    reloaded = PlatformStore(db_path=db).get_output(output.id)

    assert reloaded is not None
    assert reloaded.id == output.id


def test_store_coexists_with_the_ingestion_tables(tmp_path: Path) -> None:
    """Platform tables share the ingestion database without disturbing it."""
    from src.ingestion.store import SQLiteStore

    db = str(tmp_path / "shared.db")
    ingestion = SQLiteStore(db_path=db)
    platform = PlatformStore(db_path=db)

    platform.save_agent_run(AgentRun(agent_name="mentor"))

    assert ingestion.get_document_by_hash("does-not-exist") is None
    assert len(platform.list_agent_runs()) == 1


def test_saved_review_is_returned_unchanged(store: PlatformStore) -> None:
    output = _make_output()
    store.save_output(output)
    review = apply_review(output, "nour", ReviewAction.COMMENT, notes="looks fine")

    saved = store.save_review(review)

    assert isinstance(saved, Review)
    assert saved.notes == "looks fine"
    assert saved.action is ReviewAction.COMMENT


# --------------------------------------------------------------------------- #
# GroundedReferencesRule: the hallucinated-citation check
# --------------------------------------------------------------------------- #


def _grounded_context(*chunk_ids: str) -> GroundedContext:
    """Build a GroundedContext whose retrieved chunks have the given ids."""
    return GroundedContext(
        query="what is newton's second law",
        scope=RetrievalScope(document_id="physics-notes"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id=chunk_id,
                    document_id="physics-notes",
                    ordinal=index,
                    text=f"content of {chunk_id}",
                ),
                score=1.0 - index / 10,
                rank=index + 1,
            )
            for index, chunk_id in enumerate(chunk_ids)
        ],
    )


def _mentor_output(*segment_ids: str) -> MentorOutput:
    """A schema-valid MentorOutput citing the given segment ids."""
    return MentorOutput(
        explanation="Force equals mass times acceleration.",
        key_points=["F = ma"],
        next_steps=["Practice a worked example."],
        references=[
            ContentReference(segment_id=segment_id, text="excerpt")
            for segment_id in segment_ids
        ],
    )


def test_grounding_rule_is_a_no_op_without_a_grounded_context() -> None:
    """Ungrounded callers are not penalised; the rule simply does not apply."""
    rule = GroundedReferencesRule()

    assert rule.check(_mentor_output("anything"), GuardrailContext()) is None


def test_grounding_rule_passes_when_every_citation_was_retrieved() -> None:
    rule = GroundedReferencesRule()
    context = GuardrailContext(
        grounded_context=_grounded_context("physics-notes-c0000", "physics-notes-c0001")
    )

    assert rule.check(_mentor_output("physics-notes-c0000"), context) is None


def test_grounding_rule_flags_a_fabricated_citation() -> None:
    """The exact failure the mock agents exhibit: citing 'chunk_001'."""
    rule = GroundedReferencesRule()
    context = GuardrailContext(grounded_context=_grounded_context("physics-notes-c0000"))

    violation = rule.check(_mentor_output("chunk_001"), context)

    assert violation is not None
    assert violation.rule_name == "grounded_references"
    assert violation.severity is Severity.ERROR
    assert "chunk_001" in violation.message


def test_grounding_rule_reaches_nested_references() -> None:
    """QuestionBankOutput cites per question, not at the top level."""
    rule = GroundedReferencesRule()
    context = GuardrailContext(grounded_context=_grounded_context("physics-notes-c0000"))
    output = QuestionBankOutput(
        questions=[
            QuestionItem(
                question="What is F = ma?",
                options=["a", "b"],
                correct_answer="a",
                rationale="because",
                difficulty=DifficultyLevel.BEGINNER,
                type=QuestionType.MCQ,
                references=[ContentReference(segment_id="invented-id", text="x")],
            )
        ]
    )

    violation = rule.check(output, context)

    assert violation is not None
    assert "invented-id" in violation.message


def test_ungrounded_output_fails_validation_end_to_end() -> None:
    """Wired into DEFAULT_RULES, a fabricated citation fails the whole verdict."""
    validator = ValidatorBase()
    context = GuardrailContext(grounded_context=_grounded_context("physics-notes-c0000"))

    result, model = validator.validate(
        _mentor_output("chunk_001").model_dump(), MentorOutput, context=context
    )

    assert model is not None  # schema was fine; grounding was not
    assert result.passed is False
    assert any(v.rule_name == "grounded_references" for v in result.guardrail_violations)


def test_grounded_output_passes_validation_end_to_end() -> None:
    validator = ValidatorBase()
    context = GuardrailContext(grounded_context=_grounded_context("physics-notes-c0000"))

    result, _ = validator.validate(
        _mentor_output("physics-notes-c0000").model_dump(),
        MentorOutput,
        context=context,
    )

    assert result.passed is True
    assert result.guardrail_violations == []


def test_references_present_rule_covers_nested_citations() -> None:
    """A question with no references is ungrounded even with no top-level field."""
    rule = ReferencesPresentRule()
    output = QuestionBankOutput(
        questions=[
            QuestionItem(
                question="What is F = ma?",
                options=["a", "b"],
                correct_answer="a",
                rationale="because",
                difficulty=DifficultyLevel.BEGINNER,
                type=QuestionType.MCQ,
                references=[],
            )
        ]
    )

    assert rule.check(output, GuardrailContext()) is not None
