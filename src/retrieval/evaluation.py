"""Retrieval quality evaluation: recall@k, MRR, and a grounding-confidence signal.

The existing test suite proves the retrieval *plumbing* is correct (scope
isolation, ranking, incremental updates); it says nothing about whether
retrieval actually surfaces the right chunks for real questions. This module
closes that gap: given a small labelled set of
``(query, scope, expected_chunk_ids)`` cases, it runs them through a real
:class:`~src.retrieval.retriever.Retriever` and reports standard IR metrics,
plus a simple per-query confidence signal the calling agent (or the
validation lane) can use to decide whether to trust the grounding at all.

This module is deliberately independent of any particular embedder or demo
dataset — :mod:`src.retrieval.benchmark` wires it up against a concrete
corpus and the offline hashing embedder for CI; a labelled set over real
course material run with the live ONNX embedder (``RETRIEVAL_EMBEDDER=onnx``) is the
honest quality measurement referenced in the retrieval-lane handoff doc's
Task 5.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.retrieval.models import RetrievalScope

if TYPE_CHECKING:
    from src.retrieval.retriever import Retriever


class EvalCase(BaseModel):
    """One labelled evaluation case: a query and the chunk ids it should surface.

    Attributes:
        query: The question or search text to run.
        scope: The document/session scope to search within.
        expected_chunk_ids: Chunk ids considered a correct retrieval for this
            query. A case is a "hit" if *any* of these appear in the
            retrieved results.
    """

    query: str
    scope: RetrievalScope
    expected_chunk_ids: list[str] = Field(min_length=1)


class CaseResult(BaseModel):
    """Per-case retrieval outcome against its label.

    Attributes:
        query: The case's query, echoed for reporting.
        expected_chunk_ids: The case's label, echoed for reporting.
        retrieved_chunk_ids: What the retriever actually returned, in rank
            order.
        hit_at_k: Whether any expected chunk id was retrieved.
        reciprocal_rank: ``1 / rank`` of the first expected chunk id found,
            or ``0.0`` if none were retrieved (standard MRR contribution).
        top_score: The top-ranked result's similarity score, or ``None`` when
            nothing was retrieved.
    """

    query: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit_at_k: bool
    reciprocal_rank: float
    top_score: float | None


class EvaluationReport(BaseModel):
    """Aggregate retrieval-quality metrics over a labelled evaluation set.

    Attributes:
        case_results: Per-case detail, in input order.
        recall_at_k: Fraction of cases with at least one expected chunk
            retrieved within top_k.
        mean_reciprocal_rank: Mean of each case's reciprocal rank.
        mean_grounding_confidence: Mean of :func:`grounding_confidence` over
            every case.
    """

    case_results: list[CaseResult]
    recall_at_k: float
    mean_reciprocal_rank: float
    mean_grounding_confidence: float

    @property
    def num_cases(self) -> int:
        """Number of cases the report was built from."""
        return len(self.case_results)


def grounding_confidence(top_score: float | None, *, has_hits: bool) -> float:
    """A single 0-1 confidence signal: "how much should this grounding be trusted".

    Deliberately simple and conservative: confidence is ``0.0`` when nothing
    was retrieved, otherwise the top-ranked result's similarity score,
    clamped to ``[0, 1]``. This is a monotonic proxy a caller can threshold
    on (e.g. "warn the user below 0.3", or route to
    ``InsufficientGroundingError``-style handling) — it is intentionally
    *not* a calibrated probability of correctness, since similarity score and
    factual correctness are related but not the same thing.

    Args:
        top_score: The top retrieved chunk's similarity score, or ``None``
            when nothing was retrieved.
        has_hits: Whether any chunk was retrieved at all.

    Returns:
        A confidence value in ``[0.0, 1.0]``.
    """
    if not has_hits or top_score is None:
        return 0.0
    return max(0.0, min(1.0, top_score))


def evaluate_case(
    case: EvalCase, retriever: Retriever, *, top_k: int | None = None
) -> CaseResult:
    """Run one labelled case against a retriever and score it.

    Args:
        case: The labelled query/scope/expected-ids case.
        retriever: Any :class:`~src.retrieval.retriever.Retriever`
            implementation.
        top_k: Optional result-count override passed through to the
            retriever.

    Returns:
        The scored outcome for this single case.
    """
    results = retriever.retrieve(case.query, case.scope, top_k=top_k)
    retrieved_ids = [result.chunk.chunk_id for result in results]
    expected = set(case.expected_chunk_ids)

    hit = any(chunk_id in expected for chunk_id in retrieved_ids)
    reciprocal_rank = 0.0
    for result in results:
        if result.chunk.chunk_id in expected:
            reciprocal_rank = 1.0 / result.rank
            break

    top_score = results[0].score if results else None

    return CaseResult(
        query=case.query,
        expected_chunk_ids=case.expected_chunk_ids,
        retrieved_chunk_ids=retrieved_ids,
        hit_at_k=hit,
        reciprocal_rank=reciprocal_rank,
        top_score=top_score,
    )


def evaluate_retriever(
    cases: list[EvalCase], retriever: Retriever, *, top_k: int | None = None
) -> EvaluationReport:
    """Evaluate a retriever against a labelled set of cases.

    Args:
        cases: Labelled evaluation cases; an empty list yields a zeroed
            report rather than an error (an empty benchmark run is a valid,
            if uninformative, outcome).
        retriever: Any :class:`~src.retrieval.retriever.Retriever`
            implementation.
        top_k: Optional result-count override applied to every case.

    Returns:
        The aggregate report: recall@k, mean reciprocal rank, and mean
        grounding confidence across all cases, plus per-case detail.
    """
    if not cases:
        return EvaluationReport(
            case_results=[],
            recall_at_k=0.0,
            mean_reciprocal_rank=0.0,
            mean_grounding_confidence=0.0,
        )

    results = [evaluate_case(case, retriever, top_k=top_k) for case in cases]
    recall_at_k = sum(1 for result in results if result.hit_at_k) / len(results)
    mean_reciprocal_rank = sum(result.reciprocal_rank for result in results) / len(
        results
    )
    mean_grounding_confidence = sum(
        grounding_confidence(result.top_score, has_hits=result.hit_at_k)
        for result in results
    ) / len(results)

    return EvaluationReport(
        case_results=results,
        recall_at_k=recall_at_k,
        mean_reciprocal_rank=mean_reciprocal_rank,
        mean_grounding_confidence=mean_grounding_confidence,
    )
