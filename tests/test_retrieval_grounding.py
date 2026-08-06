"""Tests for src.retrieval.verifier and src.retrieval.evaluation.

Extends the retrieval lane's existing coverage (test_retrieval.py /
test_retrieval_pipeline.py) with the fabricated-citation guardrail and the
recall@k / MRR / grounding-confidence evaluation harness. Offline and
deterministic, following the same pattern as the rest of the suite: a
unique Chroma collection per test, hashing embedder injected explicitly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel

from src.retrieval.config import RetrievalConfig
from src.retrieval.evaluation import (
    EvalCase,
    evaluate_case,
    evaluate_retriever,
    grounding_confidence,
)
from src.retrieval.grounding import build_grounded_context
from src.retrieval.index import ChunkIndex, HashingEmbeddingFunction
from src.retrieval.models import Chunk, RetrievalScope
from src.retrieval.retriever import ChromaRetriever
from src.retrieval.verifier import (
    GroundingContextMissingError,
    GroundingVerificationRule,
)
from src.validation.guardrails import GuardrailContext
from src.validation.schemas import ContentReference, MentorOutput


def make_index(**overrides: object) -> ChunkIndex:
    """A fresh in-memory index with the deterministic offline embedder."""
    config = RetrievalConfig(
        collection_name=f"test-{uuid4().hex}",  # type: ignore[arg-type]
        **overrides,  # type: ignore[arg-type]
    )
    return ChunkIndex(config, embedding_function=HashingEmbeddingFunction())


def seeded_retriever() -> ChromaRetriever:
    """A retriever over one small physics document."""
    index = make_index()
    index.add_chunks(
        [
            Chunk(
                chunk_id="physics-notes-c0000",
                document_id="physics-notes",
                session_id="session-1",
                ordinal=0,
                text="Newton's second law states force equals mass times acceleration.",
            ),
            Chunk(
                chunk_id="physics-notes-c0001",
                document_id="physics-notes",
                session_id="session-1",
                ordinal=1,
                text="Acceleration measures how quickly velocity changes over time.",
            ),
        ]
    )
    return ChromaRetriever(index)


def make_mentor_output(references: list[ContentReference]) -> MentorOutput:
    """A minimal valid MentorOutput carrying the given references."""
    return MentorOutput(
        explanation="Force equals mass times acceleration.",
        key_points=["F = m * a"],
        next_steps=["Try a worked example with real numbers."],
        references=references,
    )


class TestGroundingVerificationRule:
    def test_passes_when_all_citations_were_retrieved(self) -> None:
        retriever = seeded_retriever()
        context = build_grounded_context(
            "newton force acceleration",
            RetrievalScope(document_id="physics-notes"),
            retriever,
        )
        output = make_mentor_output(context.to_content_references())
        rule = GroundingVerificationRule().for_context(context)
        assert rule.check(output, GuardrailContext()) is None

    def test_fails_on_fabricated_segment_id(self) -> None:
        retriever = seeded_retriever()
        context = build_grounded_context(
            "newton force acceleration",
            RetrievalScope(document_id="physics-notes"),
            retriever,
        )
        fabricated = ContentReference(segment_id="made-up-c9999", text="invented")
        output = make_mentor_output([fabricated])
        rule = GroundingVerificationRule().for_context(context)
        violation = rule.check(output, GuardrailContext())
        assert violation is not None
        assert violation.rule_name == "grounding_verification"
        assert "made-up-c9999" in violation.message

    def test_not_applicable_when_schema_has_no_references_field(self) -> None:
        class NoRefsOutput(BaseModel):
            text: str

        retriever = seeded_retriever()
        context = build_grounded_context(
            "newton force", RetrievalScope(document_id="physics-notes"), retriever
        )
        rule = GroundingVerificationRule().for_context(context)
        assert rule.check(NoRefsOutput(text="hi"), GuardrailContext()) is None

    def test_raises_when_no_context_bound(self) -> None:
        output = make_mentor_output([])
        rule = GroundingVerificationRule()
        with pytest.raises(GroundingContextMissingError):
            rule.check(output, GuardrailContext())

    def test_for_context_returns_new_instance_not_mutated_self(self) -> None:
        retriever = seeded_retriever()
        context = build_grounded_context(
            "newton force", RetrievalScope(document_id="physics-notes"), retriever
        )
        base_rule = GroundingVerificationRule()
        bound_rule = base_rule.for_context(context)
        assert bound_rule is not base_rule
        with pytest.raises(GroundingContextMissingError):
            base_rule.check(make_mentor_output([]), GuardrailContext())


class TestGroundingConfidence:
    def test_zero_when_no_hits(self) -> None:
        assert grounding_confidence(None, has_hits=False) == 0.0
        assert grounding_confidence(0.9, has_hits=False) == 0.0

    def test_matches_top_score_when_hit(self) -> None:
        assert grounding_confidence(0.83, has_hits=True) == pytest.approx(0.83)

    def test_clamped_to_unit_interval(self) -> None:
        assert grounding_confidence(1.5, has_hits=True) == 1.0
        assert grounding_confidence(-0.2, has_hits=True) == 0.0


class TestEvaluateCase:
    def test_hit_case_scores_full_reciprocal_rank(self) -> None:
        retriever = seeded_retriever()
        case = EvalCase(
            query="newton force acceleration",
            scope=RetrievalScope(document_id="physics-notes"),
            expected_chunk_ids=["physics-notes-c0000"],
        )
        result = evaluate_case(case, retriever)
        assert result.hit_at_k is True
        assert result.reciprocal_rank == pytest.approx(1.0)
        assert result.top_score is not None

    def test_miss_case_scores_zero(self) -> None:
        retriever = seeded_retriever()
        case = EvalCase(
            query="newton force acceleration",
            scope=RetrievalScope(document_id="physics-notes"),
            expected_chunk_ids=["nonexistent-c9999"],
        )
        result = evaluate_case(case, retriever)
        assert result.hit_at_k is False
        assert result.reciprocal_rank == 0.0

    def test_empty_scope_result_yields_no_top_score(self) -> None:
        retriever = seeded_retriever()
        case = EvalCase(
            query="",  # blank query -> no results, per the retriever contract
            scope=RetrievalScope(document_id="physics-notes"),
            expected_chunk_ids=["physics-notes-c0000"],
        )
        result = evaluate_case(case, retriever)
        assert result.retrieved_chunk_ids == []
        assert result.top_score is None


class TestEvaluateRetriever:
    def test_aggregate_report_over_multiple_cases(self) -> None:
        retriever = seeded_retriever()
        cases = [
            EvalCase(
                query="newton force acceleration",
                scope=RetrievalScope(document_id="physics-notes"),
                expected_chunk_ids=["physics-notes-c0000"],
            ),
            EvalCase(
                query="totally unrelated topic xyz",
                scope=RetrievalScope(document_id="physics-notes"),
                expected_chunk_ids=["nonexistent-c9999"],
            ),
        ]
        report = evaluate_retriever(cases, retriever)
        assert report.num_cases == 2
        assert 0.0 <= report.recall_at_k <= 1.0
        assert 0.0 <= report.mean_reciprocal_rank <= 1.0
        assert 0.0 <= report.mean_grounding_confidence <= 1.0
        assert len(report.case_results) == 2

    def test_perfect_recall_when_every_case_hits(self) -> None:
        retriever = seeded_retriever()
        cases = [
            EvalCase(
                query="newton force acceleration",
                scope=RetrievalScope(document_id="physics-notes"),
                expected_chunk_ids=["physics-notes-c0000"],
            ),
            EvalCase(
                query="velocity changes over time",
                scope=RetrievalScope(document_id="physics-notes"),
                expected_chunk_ids=["physics-notes-c0001"],
            ),
        ]
        report = evaluate_retriever(cases, retriever)
        assert report.recall_at_k == pytest.approx(1.0)
        assert report.mean_reciprocal_rank == pytest.approx(1.0)

    def test_empty_case_list_returns_zeroed_report(self) -> None:
        retriever = seeded_retriever()
        report = evaluate_retriever([], retriever)
        assert report.num_cases == 0
        assert report.recall_at_k == 0.0
        assert report.mean_reciprocal_rank == 0.0
        assert report.mean_grounding_confidence == 0.0

    def test_respects_top_k_override(self) -> None:
        retriever = seeded_retriever()
        case = EvalCase(
            query="newton force acceleration velocity",
            scope=RetrievalScope(document_id="physics-notes"),
            expected_chunk_ids=["physics-notes-c0001"],
        )
        report = evaluate_retriever([case], retriever, top_k=1)
        assert len(report.case_results[0].retrieved_chunk_ids) <= 1
