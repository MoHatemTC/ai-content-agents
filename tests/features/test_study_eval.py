"""Tests for the batch pipeline + groundedness quality benchmark."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.schemas import Flashcard, FlashcardSet
from src.study.batch import (
    BatchFlashcardResult,
    BatchPlanResult,
    BatchReport,
    default_demo_dataset,
    run_full_batch,
)
from src.study.evaluation import (
    BenchmarkReport,
    benchmark_quality,
)
from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_flashcard_set,
    format_revision_session,
    format_study_plan,
)
from src.study.schemas import StudyPlan, TopicSchedule
from tests.conftest import compliant_study_agents


class TestFullBatchPipeline:
    def test_default_dataset_is_non_empty(self):
        dataset = default_demo_dataset()
        assert len(dataset) == 3
        for item in dataset:
            assert item.title
            assert len(item.content) > 20

    def test_full_batch_runs_cleanly(self):
        dataset = default_demo_dataset()
        report = run_full_batch(
            dataset,
            card_format="term-definition",
            card_count=5,
            agents=compliant_study_agents(),
        )
        assert isinstance(report, BatchReport)
        summary = report.summary()
        # No agent should have errors for the default demo dataset.
        for k in ("flashcards", "plans", "revisions"):
            assert summary[k]["total"] == 3
            assert summary[k]["errors"] == 0
            assert summary[k]["ok"] == 3


class TestBenchmarkQuality:
    def test_benchmark_scores_are_high_on_clean_defaults(self):
        dataset = default_demo_dataset()
        report = run_full_batch(dataset, card_count=5, agents=compliant_study_agents())
        bench = benchmark_quality(
            report,
            dataset,
            expected_card_format="term-definition",
            expected_card_count=5,
        )
        assert isinstance(bench, BenchmarkReport)
        d = bench.to_dict()
        # Mock-mode outputs are fully deterministic and should be grounded
        # and schema-valid for the default demo dataset:
        assert d["flashcards"]["grounded_rate"] == 1.0
        assert d["plans"]["grounded_rate"] == 1.0
        assert d["revisions"]["grounded_rate"] == 1.0
        # Overall quality >= 0.8 on the default demo dataset (expect near 1.0).
        assert d["overall"] >= 0.8

    def test_flashcard_count_mismatch_is_detected(self):
        item = default_demo_dataset()[0]
        allowed = FlashcardAgent.extract_topics(item.content)
        assert len(allowed) > 1
        card = Flashcard(
            front="Term",
            back="Definition",
            format="term-definition",
            source_topic=allowed[0],
            tags=[],
        )
        card_set = FlashcardSet(
            title=item.title,
            description=None,
            cards=[card],
            source_topics=[allowed[0]],
            source_chunk_ids=[],
            needs_human_review=True,
        )
        report = BatchReport(
            flashcards=[BatchFlashcardResult(title=item.title, card_set=card_set)],
            plans=[],
            revisions=[],
        )
        bench = benchmark_quality(
            report,
            [item],
            expected_card_format="term-definition",
            expected_card_count=5,
        )
        d = bench.to_dict()
        assert d["flashcards"]["grounded"] == 1
        assert d["flashcards"]["format_matches_request"] == 1
        assert d["flashcards"]["count_matches_request"] == 0

    def test_plan_completeness_requires_all_extracted_topics(self):
        item = default_demo_dataset()[0]
        allowed = FlashcardAgent.extract_topics(item.content)
        assert len(allowed) > 1
        start = date.today()
        end = start + timedelta(days=7)
        plan = StudyPlan(
            goal="Goal",
            start_date=start,
            end_date=end,
            overall_difficulty="easy",
            available_hours_per_week=5.0,
            topic_schedule=[
                TopicSchedule(
                    topic=allowed[0],
                    start_date=start,
                    end_date=start,
                    duration_hours=1.0,
                    difficulty="easy",
                    resources=[],
                )
            ],
            source_topics=[allowed[0]],
            needs_human_review=True,
        )
        report = BatchReport(
            flashcards=[],
            plans=[BatchPlanResult(title=item.title, plan=plan)],
            revisions=[],
        )
        bench = benchmark_quality(report, [item])
        d = bench.to_dict()
        assert d["plans"]["grounded"] == 1
        assert d["plans"]["all_extracted_topics_scheduled"] == 0

    def test_benchmark_report_is_serialisable(self):
        import json

        dataset = default_demo_dataset()
        report = run_full_batch(dataset, card_count=3, agents=compliant_study_agents())
        bench = benchmark_quality(report, dataset, expected_card_count=3)
        text = json.dumps(bench.to_dict())
        assert text
        round_tripped = json.loads(text)
        assert "overall" in round_tripped
        for key in ("flashcards", "plans", "revisions"):
            assert "grounded_rate" in round_tripped[key]
            assert "overall_quality" in round_tripped[key]


class TestAllFormattersProduceSerialisableDicts:
    @pytest.mark.parametrize(
        "formatter,producer",
        [
            (format_flashcard_set, "fc"),
            (format_study_plan, "sp"),
            (format_revision_session, "rv"),
        ],
    )
    def test_formatter_outputs_are_json_safe(self, formatter, producer):
        import json

        dataset = default_demo_dataset()
        report = run_full_batch(dataset, card_count=3, agents=compliant_study_agents())
        if producer == "fc":
            obj = report.flashcards[0].card_set
        elif producer == "sp":
            obj = report.plans[0].plan
        else:
            obj = report.revisions[0].session
        as_dict = formatter(obj)
        text = json.dumps(as_dict)
        assert text
        rt = json.loads(text)
        assert rt["needs_human_review"] is True


class TestHumanReviewGateIsEnforced:
    def test_every_batch_output_remains_pending_review(self):
        dataset = default_demo_dataset()
        report = run_full_batch(dataset, agents=compliant_study_agents())
        for r in report.flashcards:
            assert r.card_set.needs_human_review is True
        for r in report.plans:
            assert r.plan is not None
            assert r.plan.needs_human_review is True
        for r in report.revisions:
            assert r.session is not None
            assert r.session.needs_human_review is True
