"""Tests for the study-plan and revision agents plus validation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.study.batch import default_demo_dataset, run_revision_batch, run_study_plan_batch
from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_revision_session,
    format_study_plan,
)
from src.study.revision_agent import (
    RevisionAgent,
    RevisionGroundingError,
)
from src.study.study_plan_agent import (
    PlanGroundingError,
    StudyPlanAgent,
)

SAMPLE_CONTENT = (
    "Python Programming Basics. Python is a high-level interpreted language. "
    "Key concepts: Functions, Loops, Classes, Lists, Dictionaries. "
    "Functions are reusable pieces of code defined with the def keyword. "
    "Loops iterate over sequences: for loops and while loops. "
    "Classes enable object-oriented programming. "
    "Lists store ordered sequences; Dictionaries map keys to values."
)


class TestStudyPlanAgent:
    def test_generate_mock_study_plan(self):
        agent = StudyPlanAgent(mock_mode=True)
        today = date.today()
        plan = agent.generate(
            SAMPLE_CONTENT,
            learner_goal="Prepare for Python exam",
            difficulty="medium",
            start_date=today,
            end_date=today + timedelta(days=28),
            hours_per_week=8.0,
        )
        assert plan.needs_human_review is True
        assert len(plan.topic_schedule) >= 1
        extracted = set(FlashcardAgent.extract_topics(SAMPLE_CONTENT))
        for s in plan.topic_schedule:
            assert s.topic in extracted
            assert s.start_date >= plan.start_date
            assert s.end_date <= plan.end_date
            assert s.difficulty in {"easy", "medium", "hard"}
            assert s.duration_hours > 0

    def test_study_plan_rejects_invalid_dates(self):
        agent = StudyPlanAgent(mock_mode=True)
        today = date.today()
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="Bad dates",
                difficulty="medium",
                start_date=today + timedelta(days=10),
                end_date=today,
            )

    def test_study_plan_rejects_bad_difficulty(self):
        agent = StudyPlanAgent(mock_mode=True)
        today = date.today()
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="Bad difficulty",
                difficulty="expert",
                start_date=today,
                end_date=today + timedelta(days=10),
            )

    def test_plan_grounding_rejects_fabricated_topic(self, monkeypatch):
        agent = StudyPlanAgent(mock_mode=True)
        original = agent._mock_response

        def _bad(*a, **kw):
            good = original(*a, **kw)
            bad = good.topic_schedule[0].model_copy(update={"topic": "Hallucinated AI Topic"})
            good.topic_schedule.append(bad)
            return good

        monkeypatch.setattr(agent, "_mock_response", _bad)
        with pytest.raises(PlanGroundingError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="x",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=10),
            )

    def test_formatter_round_trip(self):
        agent = StudyPlanAgent(mock_mode=True)
        today = date.today()
        plan = agent.generate(
            SAMPLE_CONTENT,
            learner_goal="x",
            start_date=today,
            end_date=today + timedelta(days=28),
        )
        d = format_study_plan(plan)
        import json

        assert json.dumps(d)
        assert d["needs_human_review"] is True
        # dates rendered as iso strings
        for s in d["topic_schedule"]:
            assert isinstance(s["start_date"], str)
            assert isinstance(s["end_date"], str)


class TestRevisionAgent:
    def test_generate_mock_revision(self):
        agent = RevisionAgent(mock_mode=True)
        extracted = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        # Pick 2 topics that are definitely in the allow-list.
        weak = extracted[:2] if extracted else ["Python"]
        session = agent.generate(
            SAMPLE_CONTENT,
            selected_topics=weak,
            session_date=date.today(),
        )
        assert session.needs_human_review is True
        assert len(session.items) == len(weak)
        item_topics = {i.topic for i in session.items}
        assert item_topics == set(weak)
        for item in session.items:
            assert item.difficulty in {"easy", "medium", "hard"}
            assert item.next_revision_date >= session.session_date

    def test_revision_rejects_selected_topics_not_in_content(self):
        agent = RevisionAgent(mock_mode=True)
        with pytest.raises(RevisionGroundingError):
            agent.generate(
                SAMPLE_CONTENT,
                selected_topics=["Quantum Physics 301", "Martian Geopolitics"],
                session_date=date.today(),
            )

    def test_revision_requires_selected_topics(self):
        agent = RevisionAgent(mock_mode=True)
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                selected_topics=[],
                session_date=date.today(),
            )

    def test_revision_formatter(self):
        agent = RevisionAgent(mock_mode=True)
        extracted = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        weak = extracted[:2] if extracted else ["Python"]
        session = agent.generate(
            SAMPLE_CONTENT, selected_topics=weak, session_date=date.today()
        )
        import json

        d = format_revision_session(session)
        assert json.dumps(d)
        for i in d["items"]:
            assert isinstance(i["next_revision_date"], str)


class TestBatches:
    def test_study_plan_batch(self):
        dataset = default_demo_dataset()
        results = run_study_plan_batch(dataset)
        for r in results:
            assert r.error is None
            assert r.plan is not None
            assert r.plan.needs_human_review is True

    def test_revision_batch(self):
        dataset = default_demo_dataset()
        results = run_revision_batch(dataset)
        for r in results:
            assert r.error is None
            assert r.session is not None
            assert r.session.needs_human_review is True
