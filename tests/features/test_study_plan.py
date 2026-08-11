"""Tests for the study-plan and revision agents plus validation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.study.batch import (
    default_demo_dataset,
    run_revision_batch,
    run_study_plan_batch,
)
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
from tests.conftest import FakeLLMClient, revision_reply, study_plan_reply

SAMPLE_CONTENT = (
    "Python Programming Basics. Python is a high-level interpreted language. "
    "Key concepts: Functions, Loops, Classes, Lists, Dictionaries. "
    "Functions are reusable pieces of code defined with the def keyword. "
    "Loops iterate over sequences: for loops and while loops. "
    "Classes enable object-oriented programming. "
    "Lists store ordered sequences; Dictionaries map keys to values."
)


def _plan_agent(*replies: str) -> StudyPlanAgent:
    """A study-plan agent wired to a fake gateway."""
    return StudyPlanAgent(client=FakeLLMClient(*replies), model="test-model")


def _revision_agent(*replies: str) -> RevisionAgent:
    """A revision agent wired to a fake gateway."""
    return RevisionAgent(client=FakeLLMClient(*replies), model="test-model")


def _plan_for(content: str, **kwargs) -> str:
    """A plan reply scheduling only topics the agent will extract."""
    return study_plan_reply(FlashcardAgent.extract_topics(content), **kwargs)


class TestStudyPlanAgent:
    def test_generate_study_plan(self):
        today = date.today()
        agent = _plan_agent(
            _plan_for(
                SAMPLE_CONTENT,
                start_date=today,
                end_date=today + timedelta(days=28),
                learner_goal="Prepare for Python exam",
                hours_per_week=8.0,
            )
        )
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
        today = date.today()
        agent = _plan_agent()
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="Bad dates",
                difficulty="medium",
                start_date=today + timedelta(days=10),
                end_date=today,
            )

    def test_study_plan_rejects_bad_difficulty(self):
        today = date.today()
        agent = _plan_agent()
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="Bad difficulty",
                difficulty="expert",
                start_date=today,
                end_date=today + timedelta(days=10),
            )

    def test_plan_grounding_rejects_fabricated_topic(self):
        """A scheduled topic the content never mentioned must be refused.

        This used to monkeypatch ``_mock_response`` and append to the returned
        object, which skipped the parse step - the JSON path a real
        hallucination travels was never exercised. It now arrives as JSON.
        """
        today = date.today()
        topics = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        agent = _plan_agent(
            study_plan_reply(
                [*topics[:2], "Hallucinated AI Topic"],
                start_date=today,
                end_date=today + timedelta(days=10),
            )
        )

        with pytest.raises(PlanGroundingError):
            agent.generate(
                SAMPLE_CONTENT,
                learner_goal="x",
                start_date=today,
                end_date=today + timedelta(days=10),
            )

    def test_formatter_round_trip(self):
        today = date.today()
        agent = _plan_agent(
            _plan_for(
                SAMPLE_CONTENT, start_date=today, end_date=today + timedelta(days=28)
            )
        )
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
    def test_generate_revision(self):
        extracted = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        # Pick 2 topics that are definitely in the allow-list.
        weak = extracted[:2] if extracted else ["Python"]
        agent = _revision_agent(revision_reply(weak, session_date=date.today()))
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
        agent = _revision_agent()
        with pytest.raises(RevisionGroundingError):
            agent.generate(
                SAMPLE_CONTENT,
                selected_topics=["Quantum Physics 301", "Martian Geopolitics"],
                session_date=date.today(),
            )

    def test_revision_requires_selected_topics(self):
        agent = _revision_agent()
        with pytest.raises(ValueError):
            agent.generate(
                SAMPLE_CONTENT,
                selected_topics=[],
                session_date=date.today(),
            )

    def test_revision_formatter(self):
        extracted = FlashcardAgent.extract_topics(SAMPLE_CONTENT)
        weak = extracted[:2] if extracted else ["Python"]
        agent = _revision_agent(revision_reply(weak, session_date=date.today()))
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
        today = date.today()
        replies = [
            study_plan_reply(
                FlashcardAgent.extract_topics(item.content),
                start_date=item.start_date or today,
                end_date=item.end_date or today + timedelta(days=28),
                learner_goal=item.learner_goal,
                difficulty=item.difficulty,
                hours_per_week=item.hours_per_week,
            )
            for item in dataset
        ]
        results = run_study_plan_batch(dataset, agent=_plan_agent(*replies))
        for r in results:
            assert r.error is None
            assert r.plan is not None
            assert r.plan.needs_human_review is True

    def test_revision_batch(self):
        dataset = default_demo_dataset()
        today = date.today()
        replies = []
        for item in dataset:
            weak = item.weak_topics
            if not weak:
                extracted = FlashcardAgent.extract_topics(item.content)
                weak = extracted[:2] if extracted else ["General topic"]
            replies.append(revision_reply(weak, session_date=today))
        results = run_revision_batch(dataset, agent=_revision_agent(*replies))
        for r in results:
            assert r.error is None
            assert r.session is not None
            assert r.session.needs_human_review is True
