"""One topic allow-list, supplied by whoever showed it to the learner.

Found by running the app rather than by reading it. The Revision page built its
multiselect from ``extract_topics(doc.content)`` and then handed the agent the
*retrieved* passages, so the agent re-derived a different, smaller list and
rejected a topic its own widget had just offered::

    selected_topics reference content topics that were not extracted
    from the content: ['Radiation']
    Extracted allow-list: [... 'c0001', 'c0002', 'carry', 'conduct', ...]

Two defects in one line. The second is in that allow-list: retrieved content
carries ``[chunk_id]`` marker lines, and the topic pattern read ``heat-1-c0001``
as the word ``c0001`` - so a chunk id was offered to the model as a topic to
build a flashcard about.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent, RevisionGroundingError
from src.study.study_plan_agent import StudyPlanAgent
from tests.conftest import CompliantStudyClient

DOCUMENT = (
    "Thermal conduction transfers heat through a material without bulk motion. "
    "Metals conduct heat well because free electrons carry energy through the "
    "lattice. Convection transfers heat by the bulk movement of a fluid. "
    "Radiation transfers energy by electromagnetic waves and needs no medium."
)

# What retrieval hands the agents: passages tagged with the ids the prompts ask
# the model to cite. Note it does NOT contain the radiation passage.
RETRIEVED = (
    "[heat-1-c0000]\n"
    "Thermal conduction transfers heat through a material without bulk motion.\n\n"
    "[heat-1-c0001]\n"
    "Metals conduct heat well because free electrons carry energy.\n\n"
    "[heat-1-c0002]\n"
    "Convection transfers heat by the bulk movement of a fluid."
)


def study_client() -> CompliantStudyClient:
    return CompliantStudyClient()


# --------------------------------------------------------------------------- #
# Chunk markers are not topics
# --------------------------------------------------------------------------- #


def test_chunk_ids_are_not_offered_as_topics() -> None:
    """`[heat-1-c0001]` is provenance, not something to make a flashcard about."""
    topics = FlashcardAgent.extract_topics(RETRIEVED, max_topics=40)

    assert topics, "stripping the markers removed everything"
    assert not [topic for topic in topics if topic.lower().startswith("c0")], (
        f"a chunk id was treated as a topic: {topics}"
    )


def test_stripping_markers_keeps_the_passage_text() -> None:
    """The control: removing the markers must not remove the content."""
    topics = FlashcardAgent.extract_topics(RETRIEVED, max_topics=40)

    assert "Convection" in topics
    assert "Metals" in topics


def test_a_bracketed_aside_inside_a_passage_survives() -> None:
    """Only whole-line markers go. A bracketed aside mid-sentence is real text.

    Stripping every ``[...]`` would quietly delete content, so the pattern is
    anchored to a line of its own - which is how as_prompt_content writes them.
    """
    topics = FlashcardAgent.extract_topics(
        "Thermal conduction [Faraday] moves heat through a material. "
        "Thermal conduction depends on conductivity.",
        max_topics=40,
    )

    assert "Faraday" in topics, f"a mid-line aside was stripped as a marker: {topics}"


# --------------------------------------------------------------------------- #
# The page's list is the agent's list
# --------------------------------------------------------------------------- #


def test_revision_accepts_a_topic_the_page_offered() -> None:
    """The live failure. "Radiation" is in the document, not in the passages.

    Without the explicit allow-list the agent re-derives one from RETRIEVED,
    which has no radiation passage, and rejects a topic its own page offered.
    """
    page_allow_list = FlashcardAgent.extract_topics(DOCUMENT, max_topics=40)
    assert "Radiation" in page_allow_list, "fixture no longer covers the case"

    agent = RevisionAgent(client=study_client(), model="test-model")

    session = agent.generate(
        RETRIEVED,
        selected_topics=["Radiation"],
        session_date=date(2026, 1, 1),
        extracted_topics=page_allow_list,
    )

    assert [item.topic for item in session.items] == ["Radiation"]


def test_revision_without_the_allow_list_still_rejects_an_invented_topic() -> None:
    """The guard is not weakened - only fed the right list.

    A topic in neither the document nor the passages is still refused.
    """
    agent = RevisionAgent(client=study_client(), model="test-model")

    with pytest.raises(RevisionGroundingError):
        agent.generate(
            RETRIEVED,
            selected_topics=["Photosynthesis"],
            session_date=date(2026, 1, 1),
            extracted_topics=FlashcardAgent.extract_topics(DOCUMENT, max_topics=40),
        )


def test_the_flashcard_agent_uses_the_supplied_allow_list() -> None:
    """The list reaches the prompt, so the model is constrained by it."""
    client = study_client()
    agent = FlashcardAgent(client=client, model="test-model")

    agent.generate(
        RETRIEVED,
        card_format="qa",
        card_count=2,
        extracted_topics=["Radiation", "Convection"],
    )

    prompt = client.calls[-1]["messages"][0]["content"]
    sent = json.loads(CompliantStudyClient._TOPICS.search(prompt).group(1))
    assert sent == ["Radiation", "Convection"]


def test_the_study_plan_agent_uses_the_supplied_allow_list() -> None:
    client = study_client()
    agent = StudyPlanAgent(client=client, model="test-model")

    plan = agent.generate(
        RETRIEVED,
        learner_goal="Understand heat transfer",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 28),
        extracted_topics=["Radiation", "Convection"],
    )

    assert set(plan.source_topics) <= {"Radiation", "Convection"}
    assert "Radiation" in plan.source_topics


def test_omitting_the_allow_list_still_derives_one() -> None:
    """Every existing caller passes nothing and must keep working."""
    client = study_client()
    agent = FlashcardAgent(client=client, model="test-model")

    card_set = agent.generate(DOCUMENT, card_format="qa", card_count=2)

    assert card_set.cards


# --------------------------------------------------------------------------- #
# Casing is not a grounding failure
#
# The allow-list keeps whichever spelling the document uses most, so it carries
# "conduction" - and a model writing a plan entry capitalises it. Exact string
# equality then rejected genuinely grounded output. Live:
#
#   Plan schedules topics not in extraction allow-list: ['Conduction'];
#   allowed=[... 'conduction' ...]
# --------------------------------------------------------------------------- #


def test_a_capitalised_topic_is_accepted_and_normalised() -> None:
    """Matching is case-insensitive; the allow-list's spelling is what survives."""
    assert FlashcardAgent.canonical_topic("Conduction", ["conduction"]) == "conduction"
    assert FlashcardAgent.canonical_topic("CONVECTION", ["Convection"]) == "Convection"


def test_a_topic_outside_the_list_is_still_refused() -> None:
    """The guard is loosened on casing only, not on membership."""
    assert FlashcardAgent.canonical_topic("Photosynthesis", ["conduction"]) is None
    assert FlashcardAgent.canonical_topic("", ["conduction"]) is None
    assert FlashcardAgent.canonical_topic(None, ["conduction"]) is None


def test_the_plan_accepts_a_capitalised_topic_end_to_end() -> None:
    """The live failure, at the level it actually happened."""

    class _Capitalises:
        """A model that title-cases the topic it was given, as they do."""

        def __init__(self) -> None:
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            body = json.dumps(
                {
                    "goal": "Understand heat transfer",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-28",
                    "overall_difficulty": "medium",
                    "available_hours_per_week": 10.0,
                    "topic_schedule": [
                        {
                            "topic": "Conduction",
                            "start_date": "2026-01-01",
                            "end_date": "2026-01-07",
                            "duration_hours": 4.0,
                            "difficulty": "medium",
                            "resources": [],
                        }
                    ],
                    "source_topics": ["Conduction"],
                    "needs_human_review": True,
                }
            )
            message = type("M", (), {"content": body})
            choice = type("C", (), {"message": message, "finish_reason": "stop"})
            return type("R", (), {"choices": [choice], "error": None})

    agent = StudyPlanAgent(client=_Capitalises(), model="test-model")

    plan = agent.generate(
        DOCUMENT,
        learner_goal="Understand heat transfer",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 28),
        extracted_topics=["conduction"],
    )

    assert [entry.topic for entry in plan.topic_schedule] == ["conduction"], (
        "the topic was not normalised to the allow-list spelling"
    )
    assert plan.source_topics == ["conduction"]
