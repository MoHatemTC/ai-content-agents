"""Tests for the QA foundation: review schema, validator, guardrails, and gate.

These tests exercise the lane end-to-end at the module level using plain in-memory
model instances — no database, agent, or Streamlit page is required.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from src.validation.guardrails import (
    DEFAULT_RULES,
    GuardrailContext,
    NonEmptyTextRule,
    ReferencesPresentRule,
)
from src.validation.review_schema import (
    AgentRun,
    ExportBlockedError,
    GeneratedOutput,
    IllegalTransitionError,
    OutputStatus,
    Review,
    ReviewAction,
    apply_review,
    assert_exportable,
    is_legal_transition,
)
from src.validation.validator_base import ValidatorBase


class DemoItem(BaseModel):
    """A throwaway agent-output schema used to drive the validator in tests."""

    question: str
    answer: str
    references: list[str]


def _make_output(status: OutputStatus = OutputStatus.PENDING) -> GeneratedOutput:
    """Build a GeneratedOutput in a given status for gate/lifecycle tests."""
    run = AgentRun(agent_name="demo-agent")
    return GeneratedOutput(
        agent_run_id=run.id,
        output_type="demo",
        payload={"question": "q", "answer": "a", "references": ["chunk-1"]},
        schema_name="DemoItem",
        status=status,
    )


# --------------------------------------------------------------------------- #
# Status lifecycle
# --------------------------------------------------------------------------- #


def test_generated_output_defaults_to_pending() -> None:
    assert _make_output().status is OutputStatus.PENDING


def test_is_legal_transition() -> None:
    assert is_legal_transition(OutputStatus.PENDING, OutputStatus.EDITED)
    assert is_legal_transition(OutputStatus.PENDING, OutputStatus.APPROVED)
    assert is_legal_transition(OutputStatus.EDITED, OutputStatus.APPROVED)
    # Illegal: backward moves and any move out of the terminal approved state.
    assert not is_legal_transition(OutputStatus.EDITED, OutputStatus.PENDING)
    assert not is_legal_transition(OutputStatus.APPROVED, OutputStatus.EDITED)
    assert not is_legal_transition(OutputStatus.APPROVED, OutputStatus.PENDING)


def test_apply_review_approve_from_pending() -> None:
    output = _make_output()
    review = apply_review(output, "nour", ReviewAction.APPROVE)
    assert output.status is OutputStatus.APPROVED
    assert review.previous_status is OutputStatus.PENDING
    assert review.new_status is OutputStatus.APPROVED


def test_apply_review_edit_then_approve() -> None:
    output = _make_output()
    apply_review(output, "nour", ReviewAction.EDIT, edited_payload={"question": "q2", "answer": "a2", "references": ["chunk-1"]})
    assert output.status is OutputStatus.EDITED
    apply_review(output, "nour", ReviewAction.APPROVE)
    assert output.status is OutputStatus.APPROVED


def test_apply_review_edit_updates_payload() -> None:
    output = _make_output()
    new_payload = {"question": "q2", "answer": "a2", "references": ["chunk-9"]}
    review = apply_review(output, "nour", ReviewAction.EDIT, edited_payload=new_payload)
    assert output.payload == new_payload
    assert review.edited_payload == new_payload


def test_apply_review_edit_requires_payload() -> None:
    output = _make_output()
    with pytest.raises(ValueError):
        apply_review(output, "nour", ReviewAction.EDIT)


def test_apply_review_on_approved_is_illegal() -> None:
    output = _make_output(OutputStatus.APPROVED)
    with pytest.raises(IllegalTransitionError):
        apply_review(output, "nour", ReviewAction.EDIT, edited_payload={"x": 1})


def test_apply_review_comment_keeps_status() -> None:
    output = _make_output()
    review = apply_review(output, "nour", ReviewAction.COMMENT, notes="looks off")
    assert output.status is OutputStatus.PENDING
    assert review.previous_status is review.new_status is OutputStatus.PENDING
    assert review.notes == "looks off"


def test_review_is_immutable() -> None:
    review = Review(
        output_id="o1",
        reviewer="nour",
        action=ReviewAction.APPROVE,
        previous_status=OutputStatus.PENDING,
        new_status=OutputStatus.APPROVED,
    )
    with pytest.raises(ValidationError):
        review.notes = "tampered"  # type: ignore[misc]


def test_review_history_reconstructable() -> None:
    output = _make_output()
    history: list[Review] = [
        apply_review(output, "nour", ReviewAction.EDIT, edited_payload={"question": "q", "answer": "a", "references": ["c1"]}),
        apply_review(output, "nour", ReviewAction.APPROVE),
    ]
    # The chain of statuses is continuous and ends approved.
    assert [r.new_status for r in history] == [OutputStatus.EDITED, OutputStatus.APPROVED]
    assert history[1].previous_status is history[0].new_status


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #


def test_validator_passes_valid_payload() -> None:
    result, model = ValidatorBase().validate(
        {"question": "What is X?", "answer": "X is Y.", "references": ["chunk-1"]},
        DemoItem,
    )
    assert result.passed
    assert not result.schema_errors
    assert isinstance(model, DemoItem)


def test_validator_accepts_json_string() -> None:
    result, model = ValidatorBase().validate(
        '{"question": "q", "answer": "a", "references": ["chunk-1"]}',
        DemoItem,
    )
    assert result.passed
    assert model is not None


def test_validator_reports_schema_errors_without_raising() -> None:
    # 'answer' is missing -> schema failure, reported not raised.
    result, model = ValidatorBase().validate(
        {"question": "q", "references": ["chunk-1"]},
        DemoItem,
    )
    assert not result.passed
    assert result.schema_errors
    assert model is None


def test_validator_reports_invalid_json() -> None:
    result, model = ValidatorBase().validate("{not valid json", DemoItem)
    assert not result.passed
    assert any("JSON" in err for err in result.schema_errors)
    assert model is None


def test_validator_reports_guardrail_violation() -> None:
    # Schema-valid but empty references -> grounding guardrail fails.
    result, model = ValidatorBase().validate(
        {"question": "q", "answer": "a", "references": []},
        DemoItem,
    )
    assert model is not None  # schema passed
    assert not result.passed  # but a guardrail failed
    assert any(v.rule_name == "references_present" for v in result.guardrail_violations)


# --------------------------------------------------------------------------- #
# Guardrails
# --------------------------------------------------------------------------- #


def test_references_present_rule_pass() -> None:
    item = DemoItem(question="q", answer="a", references=["chunk-1"])
    assert ReferencesPresentRule().check(item, GuardrailContext()) is None


def test_references_present_rule_fail() -> None:
    item = DemoItem(question="q", answer="a", references=[])
    violation = ReferencesPresentRule().check(item, GuardrailContext())
    assert violation is not None
    assert violation.rule_name == "references_present"


def test_references_present_rule_not_applicable() -> None:
    class NoRefs(BaseModel):
        text: str

    assert ReferencesPresentRule().check(NoRefs(text="hi"), GuardrailContext()) is None


def test_non_empty_text_rule_pass() -> None:
    item = DemoItem(question="q", answer="a", references=["chunk-1"])
    assert NonEmptyTextRule().check(item, GuardrailContext()) is None


def test_non_empty_text_rule_fail() -> None:
    item = DemoItem(question="   ", answer="a", references=["chunk-1"])
    violation = NonEmptyTextRule().check(item, GuardrailContext())
    assert violation is not None
    assert violation.rule_name == "non_empty_text"


def test_default_rules_present() -> None:
    names = {rule.name for rule in DEFAULT_RULES}
    assert {"references_present", "non_empty_text"} <= names


# --------------------------------------------------------------------------- #
# Export gate — the core promise of the lane
# --------------------------------------------------------------------------- #


def test_gate_blocks_pending() -> None:
    with pytest.raises(ExportBlockedError):
        assert_exportable(_make_output(OutputStatus.PENDING))


def test_gate_blocks_edited() -> None:
    with pytest.raises(ExportBlockedError):
        assert_exportable(_make_output(OutputStatus.EDITED))


def test_gate_allows_approved() -> None:
    assert_exportable(_make_output(OutputStatus.APPROVED))  # must not raise


def test_export_blocked_error_carries_context() -> None:
    output = _make_output(OutputStatus.PENDING)
    with pytest.raises(ExportBlockedError) as exc_info:
        assert_exportable(output)
    assert exc_info.value.output_id == output.id
    assert exc_info.value.status is OutputStatus.PENDING
