"""Typed result models for deterministic output evaluation."""

from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """Evaluation signals derived from existing validation and grounding checks."""

    grounded: bool
    references_valid: bool
    supported: bool
    validation_passed: bool
    unsupported_claims: int = Field(ge=0)
    groundedness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    groundedness_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    difficulty_alignment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
