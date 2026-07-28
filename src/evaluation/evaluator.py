"""Deterministic evaluation built on the shared validation and grounding APIs."""

from __future__ import annotations

from src.evaluation.models import EvaluationResult
from src.retrieval.grounding import verify_references
from src.retrieval.models import GroundedContext
from src.validation.schemas import (
    ConceptOutput,
    DifficultyLevel,
    MentorOutput,
    QuestionBankOutput,
    QuestionType,
    TestHelpOutput,
    validate_difficulty,
)
from src.validation.support_validator import extract_claim_text, validate_support
from src.validation.validator_base import ValidatorBase
from src.validation.guardrails import DEFAULT_RULES
from src.validation.question_rules import QuestionItemQualityRule


EvaluatedOutput = MentorOutput | ConceptOutput | QuestionBankOutput | TestHelpOutput


def _difficulty_alignment_score(
    claims: list[str],
    difficulty: str | DifficultyLevel | None,
) -> float | None:
    """Score claim length against simple deterministic difficulty bands."""
    if difficulty is None:
        return None
    level = validate_difficulty(difficulty)
    if not claims:
        return 0.0

    average_words = sum(len(claim.split()) for claim in claims) / len(claims)
    if level is DifficultyLevel.BEGINNER:
        return max(0.0, 1.0 - max(average_words - 12.0, 0.0) / 12.0)
    if level is DifficultyLevel.INTERMEDIATE:
        if average_words < 8.0:
            return max(0.0, average_words / 8.0)
        return max(0.0, 1.0 - max(average_words - 24.0, 0.0) / 24.0)
    return min(1.0, average_words / 16.0)


def _quality_score(output: EvaluatedOutput) -> float:
    """Score the presence of the four required content fields equally."""
    if isinstance(output, (QuestionBankOutput, TestHelpOutput)):
        if not output.questions:
            return 0.0
        complete = sum(
            bool(question.question.strip())
            and bool(question.correct_answer.strip())
            and bool(question.rationale.strip())
            and bool(question.references)
            for question in output.questions
        )
        return complete / len(output.questions)
    fields = (
        ("explanation", "key_points", "next_steps", "references")
        if isinstance(output, MentorOutput)
        else ("definition", "explanation", "key_points", "references")
    )
    payload = output.model_dump()

    def present(value: object) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value) and all(
                not isinstance(item, str) or bool(item.strip())
                for item in value
            )
        return bool(value)

    present_count = sum(present(payload.get(field)) for field in fields)
    return present_count / len(fields)


def evaluate_output(
    output: EvaluatedOutput,
    context: GroundedContext | None = None,
    difficulty: str | DifficultyLevel | None = None,
) -> EvaluationResult:
    """Evaluate a Mentor or Concept output using existing project utilities.

    Validation is always evaluated. Grounding signals require a supplied
    :class:`GroundedContext`; without one, no claim of grounding is made.
    The groundedness score is ``None`` when no context is supplied, zero when
    validation fails, and otherwise the sum of 0.5 for valid references and
    0.5 for supported generated claims.
    """
    validator = ValidatorBase()
    rules = (
        [*DEFAULT_RULES, QuestionItemQualityRule()]
        if isinstance(output, (QuestionBankOutput, TestHelpOutput))
        else None
    )
    validation_result, _ = validator.validate(
        output.model_dump(),
        type(output),
        rules=rules,
    )
    notes = list(validation_result.schema_errors)
    notes.extend(
        violation.message
        for violation in validation_result.guardrail_violations
    )
    quality_score = _quality_score(output)
    if isinstance(output, (QuestionBankOutput, TestHelpOutput)):
        return _evaluate_question_output(output, context, validation_result.passed, notes)

    claims = extract_claim_text(output)
    difficulty_alignment_score = _difficulty_alignment_score(claims, difficulty)

    if context is None:
        notes.append("No grounded context was supplied for evaluation.")
        return EvaluationResult(
            grounded=False,
            references_valid=False,
            supported=False,
            validation_passed=validation_result.passed,
            unsupported_claims=0,
            groundedness_score=None,
            groundedness_ratio=None,
            difficulty_alignment_score=difficulty_alignment_score,
            quality_score=quality_score,
            notes=notes,
        )

    reference_result = verify_references(output.references, context)
    support_result = validate_support(claims, context)
    references_valid = reference_result.valid
    supported = support_result.supported
    unsupported_claims = len(support_result.unsupported_claims)
    groundedness_ratio = (
        (len(claims) - unsupported_claims) / len(claims)
        if claims
        else None
    )

    if reference_result.unknown_segment_ids:
        notes.append(
            "Unknown reference ids: "
            + ", ".join(reference_result.unknown_segment_ids)
        )
    if unsupported_claims:
        notes.append(f"Unsupported claims detected: {unsupported_claims}.")
        notes.extend(
            f"Unsupported claim: {claim}"
            for claim in support_result.unsupported_claims
        )

    groundedness_score = 0.0
    if validation_result.passed:
        groundedness_score = (
            (0.5 if references_valid else 0.0)
            + (0.5 if supported else 0.0)
        )

    return EvaluationResult(
        grounded=(
            validation_result.passed
            and references_valid
            and supported
        ),
        references_valid=references_valid,
        supported=supported,
        validation_passed=validation_result.passed,
        unsupported_claims=unsupported_claims,
        groundedness_score=groundedness_score,
        groundedness_ratio=groundedness_ratio,
        difficulty_alignment_score=difficulty_alignment_score,
        quality_score=quality_score,
        notes=notes,
    )


def _evaluate_question_output(
    output: QuestionBankOutput | TestHelpOutput,
    context: GroundedContext | None,
    validation_passed: bool,
    notes: list[str],
) -> EvaluationResult:
    """Evaluate question-level citations and answer/rationale support."""
    quality_score = _quality_score(output)
    if context is None:
        notes.append("No grounded context was supplied for evaluation.")
        return EvaluationResult(
            grounded=False,
            references_valid=False,
            supported=False,
            validation_passed=validation_passed,
            unsupported_claims=0,
            groundedness_score=None,
            groundedness_ratio=None,
            quality_score=quality_score,
            notes=notes,
        )

    valid_references = True
    supported_questions = 0
    unsupported_claims = 0
    for index, question in enumerate(output.questions or [], start=1):
        verification = verify_references(question.references, context)
        valid_references = valid_references and verification.valid
        cited_ids = {
            reference.segment_id
            for reference in (question.references or [])
            if reference is not None and getattr(reference, "segment_id", None) is not None
        }
        cited_context = context.model_copy(
            update={
                "chunks": [
                    chunk for chunk in context.chunks
                    if chunk.chunk.chunk_id in cited_ids
                ]
            }
        )
        claims = [q for q in [question.rationale] if q]
        if question.type is not QuestionType.TRUE_FALSE and question.correct_answer:
            claims.insert(0, question.correct_answer)
        support = validate_support(claims, cited_context)
        if support.supported and verification.valid:
            supported_questions += 1
        else:
            unsupported_claims += len(support.unsupported_claims)
            notes.append(f"Question {index} is not fully grounded.")

    total = len(output.questions)
    ratio = supported_questions / total if total else 0.0
    grounded = validation_passed and valid_references and supported_questions == total
    score = ratio if validation_passed else 0.0
    return EvaluationResult(
        grounded=grounded,
        references_valid=valid_references,
        supported=supported_questions == total,
        validation_passed=validation_passed,
        unsupported_claims=unsupported_claims,
        groundedness_score=score,
        groundedness_ratio=ratio,
        quality_score=quality_score,
        notes=notes,
    )
