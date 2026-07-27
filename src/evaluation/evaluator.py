"""Deterministic evaluation built on the shared validation and grounding APIs."""

from __future__ import annotations

from src.evaluation.models import EvaluationResult
from src.retrieval.grounding import verify_references
from src.retrieval.models import GroundedContext
from src.validation.schemas import ConceptOutput, MentorOutput
from src.validation.support_validator import extract_claim_text, validate_support
from src.validation.validator_base import ValidatorBase


EvaluatedOutput = MentorOutput | ConceptOutput


def _quality_score(output: EvaluatedOutput) -> float:
    """Score the presence of the four required content fields equally."""
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
) -> EvaluationResult:
    """Evaluate a Mentor or Concept output using existing project utilities.

    Validation is always evaluated. Grounding signals require a supplied
    :class:`GroundedContext`; without one, no claim of grounding is made.
    The groundedness score is ``None`` when no context is supplied, zero when
    validation fails, and otherwise the sum of 0.5 for valid references and
    0.5 for supported generated claims.
    """
    validator = ValidatorBase()
    validation_result, _ = validator.validate(
        output.model_dump(),
        type(output),
    )
    notes = list(validation_result.schema_errors)
    notes.extend(
        violation.message
        for violation in validation_result.guardrail_violations
    )
    quality_score = _quality_score(output)

    if context is None:
        notes.append("No grounded context was supplied for evaluation.")
        return EvaluationResult(
            grounded=False,
            references_valid=False,
            supported=False,
            validation_passed=validation_result.passed,
            unsupported_claims=0,
            groundedness_score=None,
            quality_score=quality_score,
            notes=notes,
        )

    reference_result = verify_references(output.references, context)
    support_result = validate_support(extract_claim_text(output), context)
    references_valid = reference_result.valid
    supported = support_result.supported
    unsupported_claims = len(support_result.unsupported_claims)

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
        quality_score=quality_score,
        notes=notes,
    )
