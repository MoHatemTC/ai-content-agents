"""Offline benchmark orchestration for Mentor and Concept generation."""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field

from src.evaluation.evaluator import EvaluatedOutput, evaluate_output
from src.evaluation.models import EvaluationResult
from src.retrieval.models import GroundedContext
from src.validation.schemas import QuestionBankOutput, TestHelpOutput


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
    question_type: str | None = None
    num_questions: int | None = Field(default=None, ge=1)
    expected_answers: list[str] | None = None


class BenchmarkItemResult(BaseModel):
    """Generation and evaluation outcome for one benchmark input."""

    index: int = Field(ge=0)
    input_item: BenchmarkInput
    output: EvaluatedOutput | None = None
    evaluation: EvaluationResult | None = None
    error: str | None = None
    answer_key_sample_total: int = Field(default=0, ge=0)
    answer_key_sample_correct: int = Field(default=0, ge=0)


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
    grounded_question_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    answer_key_sample_total: int = Field(default=0, ge=0)
    answer_key_sample_correct: int = Field(default=0, ge=0)
    answer_key_sample_correctness_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )


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
            generate_args: dict[str, object] = {
                "content": input_item.content,
                "user_question": input_item.user_question,
                "difficulty": input_item.difficulty,
                "context": input_item.context,
            }
            if input_item.question_type is not None:
                generate_args["question_type"] = input_item.question_type
            if input_item.num_questions is not None:
                generate_args["num_questions"] = input_item.num_questions
            output = agent.generate(**generate_args)
            evaluation = evaluate_output(
                output,
                input_item.context,
                difficulty=input_item.difficulty,
            )
            sample_total = 0
            sample_correct = 0
            if isinstance(output, (QuestionBankOutput, TestHelpOutput)) and input_item.expected_answers:
                sample_total = min(len(output.questions), len(input_item.expected_answers))
                sample_correct = sum(
                    generated.correct_answer.strip().casefold()
                    == expected.strip().casefold()
                    for generated, expected in zip(
                        output.questions[:sample_total],
                        input_item.expected_answers[:sample_total],
                    )
                )
            item_results.append(
                BenchmarkItemResult(
                    index=index,
                    input_item=input_item,
                    output=output,
                    evaluation=evaluation,
                    answer_key_sample_total=sample_total,
                    answer_key_sample_correct=sample_correct,
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
        result.evaluation
        for result in item_results
        if result.evaluation is not None
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
    answer_sample_total = sum(item.answer_key_sample_total for item in item_results)
    answer_sample_correct = sum(item.answer_key_sample_correct for item in item_results)
    question_evaluations = [
        item.evaluation
        for item in item_results
        if isinstance(item.output, (QuestionBankOutput, TestHelpOutput))
        and item.evaluation is not None
    ]

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
        grounded_question_rate=(
            sum(evaluation.groundedness_ratio or 0.0 for evaluation in question_evaluations)
            / len(question_evaluations)
            if question_evaluations
            else None
        ),
        answer_key_sample_total=answer_sample_total,
        answer_key_sample_correct=answer_sample_correct,
        answer_key_sample_correctness_rate=(
            answer_sample_correct / answer_sample_total if answer_sample_total else None
        ),
    )
    return BenchmarkReport(item_results=item_results, summary=summary)
