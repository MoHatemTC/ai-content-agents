"""The study lane's review gate has to gate something.

Flashcards, study plans and revision sessions each set
``needs_human_review=True`` and each carried a docstring telling the caller to
route the result through :mod:`src.validation.review_schema`. No caller did -
not ``src/app.py``, not ``src/study/ui.py``, not ``src/study/batch.py`` - and
nothing in the lane referenced ``PlatformStore`` at all. The pages printed
"pending review" while the reviewer's queue stayed empty.

The second half of the same bug: two of the three agents stamped the run id
into a field the learner reads, so the audit trail that never reached the
database *did* reach the screen.
"""

from __future__ import annotations

import json

import pytest

from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent
from src.validation.review_schema import OutputStatus, RunStatus
from src.validation.store import PlatformStore
from tests.conftest import FakeLLMClient

CONTENT = (
    "An electric field is the region around a charge where a force acts. "
    "Electric potential is the work per unit charge. "
    "Capacitance measures stored charge per volt."
)


def a_flashcard_reply() -> str:
    return json.dumps(
        {
            "title": "Electrostatics",
            "description": "Cards covering fields and potential.",
            "cards": [
                {
                    "front": "What is an electric field?",
                    "back": "The region around a charge where a force acts.",
                    "source_topic": "electric",
                }
            ],
            "source_topics": ["electric"],
            "needs_human_review": True,
        }
    )


def a_revision_reply() -> str:
    return json.dumps(
        {
            "session_date": "2026-08-10",
            "items": [
                {
                    "topic": "electric",
                    "description": "Revisit how field strength falls with distance.",
                    "difficulty": "medium",
                    "next_revision_date": "2026-08-13",
                    "confidence_prompt": "Can you state the definition unaided?",
                }
            ],
            "notes": "Focus on the field section.",
            "selected_weak_topics": ["electric"],
            "source_topics": ["electric"],
            "needs_human_review": True,
        }
    )


def a_plan_reply() -> str:
    return json.dumps(
        {
            "goal": "Pass the electrostatics exam",
            "start_date": "2026-08-10",
            "end_date": "2026-08-20",
            "overall_difficulty": "medium",
            "available_hours_per_week": 6.0,
            "topic_schedule": [
                {
                    "topic": "electric",
                    "start_date": "2026-08-10",
                    "end_date": "2026-08-14",
                    "duration_hours": 3.0,
                    "difficulty": "medium",
                }
            ],
            "source_topics": ["electric"],
            "needs_human_review": True,
        }
    )


# (agent class, reply body, kwargs for generate_reviewable, expected output_type)
AGENTS = [
    pytest.param(
        FlashcardAgent, a_flashcard_reply, {"card_count": 1}, "flashcard_set",
        id="flashcard",
    ),
    pytest.param(
        RevisionAgent,
        a_revision_reply,
        {"selected_topics": ["electric"], "session_date": "2026-08-10"},
        "revision_session",
        id="revision",
    ),
    pytest.param(
        StudyPlanAgent,
        a_plan_reply,
        {
            "learner_goal": "Pass the electrostatics exam",
            "start_date": "2026-08-10",
            "end_date": "2026-08-20",
        },
        "study_plan",
        id="study_plan",
    ),
]


@pytest.mark.parametrize("agent_class,reply,kwargs,output_type", AGENTS)
def test_the_output_reaches_the_review_queue(
    agent_class, reply, kwargs, output_type, tmp_path
) -> None:
    """The bug this file exists for."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_class(client=FakeLLMClient(reply()), model="m")

    output = agent.generate_reviewable(CONTENT, store=store, **kwargs)

    queued = store.list_outputs(status=OutputStatus.PENDING)
    assert [o.id for o in queued] == [output.id], "the output never reached the queue"
    assert output.output_type == output_type


@pytest.mark.parametrize("agent_class,reply,kwargs,output_type", AGENTS)
def test_the_run_is_recorded_with_what_the_model_saw(
    agent_class, reply, kwargs, output_type, tmp_path
) -> None:
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_class(client=FakeLLMClient(reply()), model="m")

    output = agent.generate_reviewable(CONTENT, store=store, **kwargs)

    run = store.get_agent_run(output.agent_run_id)
    assert run is not None, "the run was not persisted"
    assert run.input_context == CONTENT
    assert run.finished_at is not None, "the run was left unfinished"
    assert run.status is RunStatus.SUCCESS


@pytest.mark.parametrize("agent_class,reply,kwargs,output_type", AGENTS)
def test_a_failed_run_is_recorded_not_lost(
    agent_class, reply, kwargs, output_type, tmp_path
) -> None:
    """A run that raises is a fact about the run. Without this, History shows
    it hanging in SUCCESS forever."""
    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    agent = agent_class(client=FakeLLMClient("not json at all"), model="m")

    with pytest.raises(Exception):
        agent.generate_reviewable(CONTENT, store=store, **kwargs)

    runs = store.list_agent_runs()
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILURE
    assert runs[0].error


# --------------------------------------------------------------------------- #
# The audit trail belongs in the database, not in the learner's face
# --------------------------------------------------------------------------- #


def test_a_flashcard_description_carries_no_run_id() -> None:
    """``description`` is rendered verbatim at app.py:531.

    It used to read "Cards covering fields and potential. [run_id=fc-a1b2c3d4-
    20260809143022 pending_review]".
    """
    agent = FlashcardAgent(client=FakeLLMClient(a_flashcard_reply()), model="m")

    card_set = agent.generate(CONTENT, card_count=1)

    assert card_set.description == "Cards covering fields and potential."
    assert "run_id" not in (card_set.description or "")
    assert card_set.needs_human_review is True, "the flag itself must survive"


def test_revision_notes_carry_no_run_id() -> None:
    """``notes`` is rendered as a caption at app.py:668."""
    agent = RevisionAgent(client=FakeLLMClient(a_revision_reply()), model="m")

    session = agent.generate(
        CONTENT, selected_topics=["electric"], session_date="2026-08-10"
    )

    assert session.notes == "Focus on the field section."
    assert "run_id" not in (session.notes or "")
    assert session.needs_human_review is True
