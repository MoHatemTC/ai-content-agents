"""End-to-end integration regression test for Question Bank & Test Help review pipeline."""

import pytest

from src.retrieval.models import Chunk, GroundedContext, RetrievedChunk, RetrievalScope
from src.services.question_bank import QuestionBankService
from src.validation.question_rules import QuestionItemQualityRule
from src.validation.review_schema import ExportBlockedError, OutputStatus, assert_exportable
from src.validation.schemas import QuestionBankOutput, TestHelpOutput


def _build_grounded_context() -> GroundedContext:
    """Construct a multi-chunk GroundedContext representing retrieved educational content."""
    return GroundedContext(
        query="Python loop control structures",
        scope=RetrievalScope(document_id="doc-python-basics"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk_001",
                    document_id="doc-python-basics",
                    ordinal=0,
                    text="Python provides two primary loop types: for loops and while loops.",
                ),
                score=0.95,
                rank=1,
            ),
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk_002",
                    document_id="doc-python-basics",
                    ordinal=1,
                    text="A for loop iterates over sequences, while a while loop repeats as long as a condition is true.",
                ),
                score=0.90,
                rank=2,
            ),
        ],
    )


@pytest.mark.parametrize(
    "service_method, expected_output_type, expected_schema",
    [
        ("generate_question_bank_reviewable", "question_bank", QuestionBankOutput),
        ("generate_test_help_reviewable", "test_help", TestHelpOutput),
    ],
)
def test_question_bank_end_to_end_review_pipeline(
    service_method: str, expected_output_type: str, expected_schema: type
):
    """
    Verify the complete Question Bank review workflow:
    GroundedContext -> QuestionBankService -> Agent -> Validation -> Review Gate -> GeneratedOutput
    """
    context = _build_grounded_context()
    valid_chunk_ids = {retrieved.chunk.chunk_id for retrieved in context.chunks}

    # 1. Initialize Service in Mock Mode (offline execution)
    service = QuestionBankService(mock_mode=True)

    # 2. Invoke Reviewable Generation through Service Layer (never bypassing the service)
    generate_fn = getattr(service, service_method)
    output = generate_fn(
        content=context.as_prompt_content(),
        question_type="mcq",
        difficulty="beginner",
        num_questions=2,
        context=context,
    )

    # 3. Verify Review Lifecycle & Output Status
    assert output.status is OutputStatus.PENDING
    assert output.output_type == expected_output_type
    assert output.agent_run_id is not None
    assert output.validation_passed is True

    # 4. Verify Validation Report Details
    assert output.validation_report["passed"] is True
    assert output.validation_report["schema_errors"] == []
    assert output.validation_report["guardrail_violations"] == []

    # 5. Verify Payload & Schema Invariants
    payload = output.payload
    assert payload["requires_human_review"] is True
    assert "questions" in payload
    assert len(payload["questions"]) == 2

    # Parse payload back into typed schema to verify structure
    parsed_model = expected_schema.model_validate(payload)
    assert parsed_model.requires_human_review is True

    # 6. Verify Question Content, References, Rationale, and Grounding Provenance
    for question in parsed_model.questions:
        assert question.question.strip()
        assert question.correct_answer.strip()
        assert question.rationale.strip()
        assert question.references

        # Ensure all referenced segment IDs belong to the input GroundedContext
        for reference in question.references:
            assert reference.segment_id in valid_chunk_ids
            assert reference.text.strip()

        # For MCQ: ensure correct_answer is in options and options are valid
        if question.options is not None:
            assert len(question.options) >= 4
            assert len(set(question.options)) == len(question.options)
            assert question.correct_answer in question.options

    # 7. Run Objective Guardrail Rule directly to assert zero quality violations
    quality_violation = QuestionItemQualityRule().check(parsed_model, None)
    assert quality_violation is None

    # 8. Assert Human Review Gate protection (Export must be blocked while PENDING)
    with pytest.raises(ExportBlockedError):
        assert_exportable(output)
