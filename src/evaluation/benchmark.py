"""Offline benchmark orchestration for Mentor and Concept generation."""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field

from src.evaluation.evaluator import EvaluatedOutput, evaluate_output
from src.evaluation.models import EvaluationResult
from src.retrieval.models import GroundedContext


class BenchmarkAgent(Protocol):
    """The existing generation interface required by the benchmark runner."""

    def generate(
        self,
        content: str,
        user_question: str | None = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> EvaluatedOutput:
        """Generate one typed agent output."""


class BenchmarkInput(BaseModel):
    """One input to generate and evaluate during a benchmark run."""

    content: str
    user_question: str | None = None
    difficulty: str = "beginner"
    context: GroundedContext | None = None


class BenchmarkItemResult(BaseModel):
    """Generation and evaluation outcome for one benchmark input."""

    index: int = Field(ge=0)
    input_item: BenchmarkInput
    output: EvaluatedOutput | None = None
    evaluation: EvaluationResult | None = None
    error: str | None = None


class BenchmarkSummary(BaseModel):
    """Aggregate deterministic metrics for one benchmark run."""

    total_processed: int = Field(ge=0)
    total_succeeded: int = Field(ge=0)
    total_failed: int = Field(ge=0)
    average_groundedness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_groundedness_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    average_difficulty_alignment_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    average_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reference_validity_rate: float = Field(ge=0.0, le=1.0)
    support_rate: float = Field(ge=0.0, le=1.0)
    validation_pass_rate: float = Field(ge=0.0, le=1.0)
    elapsed_seconds: float = Field(ge=0.0)


class BenchmarkReport(BaseModel):
    """Complete per-item and aggregate outcome of a benchmark run."""

    item_results: list[BenchmarkItemResult] = Field(default_factory=list)
    summary: BenchmarkSummary


def _rate(values: list[bool]) -> float:
    """Return the share of true values, or zero for an empty population."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def run_benchmark(
    agent: BenchmarkAgent,
    inputs: list[BenchmarkInput],
) -> BenchmarkReport:
    """Generate and evaluate all inputs while recording failures independently."""
    started_at = perf_counter()
    item_results: list[BenchmarkItemResult] = []

    for index, input_item in enumerate(inputs):
        try:
            output = agent.generate(
                content=input_item.content,
                user_question=input_item.user_question,
                difficulty=input_item.difficulty,
                context=input_item.context,
            )
            evaluation = evaluate_output(
                output,
                input_item.context,
                difficulty=input_item.difficulty,
            )
            item_results.append(
                BenchmarkItemResult(
                    index=index,
                    input_item=input_item,
                    output=output,
                    evaluation=evaluation,
                )
            )
        except Exception as error:
            item_results.append(
                BenchmarkItemResult(
                    index=index,
                    input_item=input_item,
                    error=str(error),
                )
            )

    evaluations = [
        result.evaluation for result in item_results if result.evaluation is not None
    ]
    scores = [
        evaluation.groundedness_score
        for evaluation in evaluations
        if evaluation.groundedness_score is not None
    ]
    quality_scores = [evaluation.quality_score for evaluation in evaluations]
    groundedness_ratios = [
        evaluation.groundedness_ratio
        for evaluation in evaluations
        if evaluation.groundedness_ratio is not None
    ]
    difficulty_scores = [
        evaluation.difficulty_alignment_score
        for evaluation in evaluations
        if evaluation.difficulty_alignment_score is not None
    ]
    succeeded = len(evaluations)
    elapsed_seconds = perf_counter() - started_at

    summary = BenchmarkSummary(
        total_processed=len(inputs),
        total_succeeded=succeeded,
        total_failed=len(inputs) - succeeded,
        average_groundedness_score=(sum(scores) / len(scores)) if scores else None,
        average_groundedness_ratio=(
            sum(groundedness_ratios) / len(groundedness_ratios)
            if groundedness_ratios
            else None
        ),
        average_difficulty_alignment_score=(
            sum(difficulty_scores) / len(difficulty_scores)
            if difficulty_scores
            else None
        ),
        average_quality_score=(sum(quality_scores) / len(quality_scores))
        if quality_scores
        else 0.0,
        reference_validity_rate=_rate(
            [evaluation.references_valid for evaluation in evaluations]
        ),
        support_rate=_rate([evaluation.supported for evaluation in evaluations]),
        validation_pass_rate=_rate(
            [evaluation.validation_passed for evaluation in evaluations]
        ),
        elapsed_seconds=elapsed_seconds,
    )
    return BenchmarkReport(item_results=item_results, summary=summary)
