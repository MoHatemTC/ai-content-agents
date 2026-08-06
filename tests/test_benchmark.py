"""Offline tests for benchmark orchestration and metric aggregation."""

from src.evaluation import BenchmarkInput, run_benchmark
from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.schemas import ContentReference, MentorOutput


def _context() -> GroundedContext:
    """Build a context that supports the standard benchmark output."""
    return GroundedContext(
        query="What is a loop?",
        scope=RetrievalScope(document_id="document-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk-1",
                    document_id="document-1",
                    ordinal=0,
                    text=(
                        "A loop repeats instructions. Loops repeat instructions. "
                        "Practice loops."
                    ),
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def _output(reference_id: str = "chunk-1") -> MentorOutput:
    """Build a valid Mentor output with a configurable citation id."""
    return MentorOutput(
        explanation="A loop repeats instructions.",
        key_points=["Loops repeat instructions."],
        next_steps=["Practice loops."],
        references=[ContentReference(segment_id=reference_id, text="Loops.")],
    )


class StubAgent:
    """A deterministic implementation of the existing generation interface."""

    def __init__(self, outcomes: dict[str, MentorOutput | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def generate(self, content: str, **_: object) -> MentorOutput:
        self.calls.append(content)
        outcome = self.outcomes[content]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_run_benchmark_all_success():
    """All generated outputs are evaluated and aggregated."""
    agent = StubAgent({"first": _output(), "second": _output()})
    inputs = [
        BenchmarkInput(content="first", context=_context()),
        BenchmarkInput(content="second", context=_context()),
    ]

    report = run_benchmark(agent, inputs)

    assert agent.calls == ["first", "second"]
    assert report.summary.total_processed == 2
    assert report.summary.total_succeeded == 2
    assert report.summary.total_failed == 0
    assert report.summary.average_groundedness_score == 1.0
    assert report.summary.average_groundedness_ratio == 1.0
    assert report.summary.average_difficulty_alignment_score is not None
    assert report.summary.average_quality_score == 1.0
    assert report.summary.reference_validity_rate == 1.0
    assert report.summary.support_rate == 1.0
    assert report.summary.validation_pass_rate == 1.0


def test_run_benchmark_continues_after_partial_failure():
    """A failed generation does not prevent later inputs from evaluation."""
    agent = StubAgent(
        {
            "first": _output(),
            "bad": ValueError("generation failed"),
            "third": _output(),
        }
    )
    inputs = [
        BenchmarkInput(content="first", context=_context()),
        BenchmarkInput(content="bad", context=_context()),
        BenchmarkInput(content="third", context=_context()),
    ]

    report = run_benchmark(agent, inputs)

    assert agent.calls == ["first", "bad", "third"]
    assert report.summary.total_processed == 3
    assert report.summary.total_succeeded == 2
    assert report.summary.total_failed == 1
    assert report.item_results[1].error == "generation failed"
    assert report.item_results[2].evaluation is not None


def test_run_benchmark_handles_empty_inputs():
    """An empty benchmark produces zero counts and no aggregate score."""
    agent = StubAgent({})

    report = run_benchmark(agent, [])

    assert agent.calls == []
    assert report.item_results == []
    assert report.summary.total_processed == 0
    assert report.summary.total_succeeded == 0
    assert report.summary.total_failed == 0
    assert report.summary.average_groundedness_score is None
    assert report.summary.reference_validity_rate == 0.0
    assert report.summary.support_rate == 0.0
    assert report.summary.validation_pass_rate == 0.0


def test_run_benchmark_aggregates_metrics_and_ignores_none_scores():
    """Only evaluated scores contribute to the groundedness average."""
    agent = StubAgent(
        {
            "grounded": _output(),
            "invalid-reference": _output(reference_id="unknown"),
            "no-context": _output(),
        }
    )
    inputs = [
        BenchmarkInput(content="grounded", context=_context()),
        BenchmarkInput(content="invalid-reference", context=_context()),
        BenchmarkInput(content="no-context"),
    ]

    report = run_benchmark(agent, inputs)

    assert report.summary.average_groundedness_score == 0.75
    assert report.summary.reference_validity_rate == 1 / 3
    assert report.summary.support_rate == 2 / 3
    assert report.summary.validation_pass_rate == 1.0
    assert report.summary.elapsed_seconds >= 0.0
