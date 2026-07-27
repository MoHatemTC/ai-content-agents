"""
Support validation for grounded AI explanations.

Ensures that generated explanations are backed by the retrieved
content rather than containing unsupported claims.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.retrieval.models import GroundedContext


class SupportValidationResult(BaseModel):
    """
    Result of checking whether an explanation is supported
    by the retrieved content.
    """

    supported: bool
    unsupported_claims: list[str]


def validate_support(
    explanation: str,
    context: GroundedContext,
) -> SupportValidationResult:
    """
    Validate that an explanation is supported by the retrieved chunks.

    Current implementation:
    - Concatenates all retrieved chunk text.
    - If the explanation is completely absent from the retrieved
      content, it is flagged for review.

    This will become more advanced in later iterations.
    """

    source_text = " ".join(
        chunk.chunk.text
        for chunk in context.chunks
    ).lower()

    explanation = explanation.lower()

    if explanation in source_text:
        return SupportValidationResult(
            supported=True,
            unsupported_claims=[],
        )

    return SupportValidationResult(
        supported=False,
        unsupported_claims=[
            explanation
        ],
    )