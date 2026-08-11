"""The study prompts' structure and their rendered variable block.

Two things are pinned here, and they fail for different reasons.

**Structure.** All seven agents are supposed to share one prompt format. The
study lane used to carry a different one - ``system_prompt`` plus
``output_schema: FlashcardSet``, a label that was never sent to the model - and
nothing detected the divergence because nobody diffs two YAML files that are
supposed to look alike.

**The rendered variable block.** ``CompliantStudyClient`` in ``conftest`` reads
its answer back out of the prompt with regexes, because a queued reply is no
use when the retriever decides which topics show up. That makes the rendered
``key: value`` lines a contract between the agents and their test double - one
nobody wrote down, so rewording a prompt could turn the entire study-lane suite
red with a failure that points at the double instead of at the prompt.

Two traps worth knowing before editing a study prompt:

* ``re.search`` returns the *first* match, and ``difficulty:\\s*(\\S+)`` matches
  prose just as happily as the variable line. The variable block must stay
  ahead of the prose. JSON keys are safe - ``"difficulty": "medium"`` has a
  quote between the word and the colon.
* The double routes on which keys are present (``session_date`` first, then
  ``card_count``, then ``start_date``/``end_date``), so those keys have to stay
  unique to their own agent.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from tests.conftest import CompliantStudyClient

import src.study as study_pkg
from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent

PROMPTS_DIR = Path(study_pkg.__file__).resolve().parent / "prompts"


def load_prompt_yaml(filename: str) -> dict:
    return yaml.safe_load((PROMPTS_DIR / filename).read_text(encoding="utf-8"))

# The shape src/prompts/mentor.yaml and concept.yaml already use. Order matters:
# a reader should be able to open any of the seven and find the same sections in
# the same places.
EXPECTED_KEYS = [
    "name",
    "description",
    "role",
    "instructions",
    "output_schema",
    "notes",
    "prompt_template",
]

TOPICS = ["Kinetic Energy", "Mitosis"]


@pytest.fixture
def flashcard_prompt() -> str:
    agent = FlashcardAgent(client=object(), model="test-model")
    return agent._build_prompt(
        "Body text about kinetic energy and mitosis.",
        TOPICS,
        "qa",
        7,
    )


@pytest.fixture
def study_plan_prompt() -> str:
    agent = StudyPlanAgent(client=object(), model="test-model")
    return agent._build_prompt(
        TOPICS,
        "Pass the exam",
        "hard",
        date(2026, 1, 1),
        date(2026, 1, 28),
        12.5,
    )


@pytest.fixture
def revision_prompt() -> str:
    agent = RevisionAgent(client=object(), model="test-model")
    return agent._build_prompt(TOPICS, ["Mitosis"], date(2026, 3, 4))


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "filename",
    ["flashcards.yaml", "study_plan.yaml", "revision.yaml"],
)
def test_study_prompts_use_the_shared_seven_section_shape(filename: str) -> None:
    data = load_prompt_yaml(filename)

    assert list(data) == EXPECTED_KEYS, (
        f"{filename} does not match the shape used by src/prompts/mentor.yaml"
    )


@pytest.mark.parametrize(
    "filename",
    ["flashcards.yaml", "study_plan.yaml", "revision.yaml"],
)
def test_output_schema_is_an_example_not_a_bare_label(filename: str) -> None:
    """A string here means the model is told a schema name and never shown it.

    That is what produced the original failure: `output_schema: FlashcardSet`,
    a guessed `{"cards": [...]}` reply, and a missing required `title`.
    """
    data = load_prompt_yaml(filename)

    assert isinstance(data["output_schema"], dict), (
        f"{filename} output_schema is a bare label, not an example structure"
    )
    assert data["output_schema"].get("needs_human_review") is True, (
        f"{filename} example omits the review-gate flag"
    )


# --------------------------------------------------------------------------- #
# The rendered variable block — what the test double parses
# --------------------------------------------------------------------------- #


def test_flashcard_prompt_carries_what_the_double_reads(flashcard_prompt: str) -> None:
    topics = CompliantStudyClient._TOPICS.search(flashcard_prompt)
    card_format = CompliantStudyClient._FORMAT.search(flashcard_prompt)
    card_count = CompliantStudyClient._COUNT.search(flashcard_prompt)

    assert topics and json.loads(topics.group(1)) == TOPICS
    assert card_format and card_format.group(1) == "qa"
    assert card_count and card_count.group(1) == "7"


def test_study_plan_prompt_carries_what_the_double_reads(
    study_plan_prompt: str,
) -> None:
    client = CompliantStudyClient

    topics = client._TOPICS.search(study_plan_prompt)
    assert topics and json.loads(topics.group(1)) == TOPICS

    # difficulty and hours_per_week accept any non-space run, so these two are
    # the ones that break when prose drifts in front of the variable block.
    assert client._GOAL.search(study_plan_prompt).group(1).strip() == "Pass the exam"
    assert client._DIFFICULTY.search(study_plan_prompt).group(1) == "hard"
    assert client._START.search(study_plan_prompt).group(1) == "2026-01-01"
    assert client._END.search(study_plan_prompt).group(1) == "2026-01-28"
    assert client._HOURS.search(study_plan_prompt).group(1) == "12.5"


def test_revision_prompt_carries_what_the_double_reads(revision_prompt: str) -> None:
    client = CompliantStudyClient

    topics = client._TOPICS.search(revision_prompt)
    selected = client._SELECTED.search(revision_prompt)
    session = client._SESSION.search(revision_prompt)

    assert topics and json.loads(topics.group(1)) == TOPICS
    assert selected and json.loads(selected.group(1)) == ["Mitosis"]
    assert session and session.group(1) == "2026-03-04"


def test_an_unset_weekly_budget_still_renders_a_parseable_line() -> None:
    """`hours_per_week` is optional; the line must not vanish or read as None."""
    agent = StudyPlanAgent(client=object(), model="test-model")
    prompt = agent._build_prompt(
        TOPICS, "Pass the exam", "easy", date(2026, 1, 1), date(2026, 1, 28), None
    )

    assert CompliantStudyClient._HOURS.search(prompt).group(1) == "unspecified"


# --------------------------------------------------------------------------- #
# Routing — the double picks an agent by which keys are present
# --------------------------------------------------------------------------- #


def test_only_the_revision_prompt_mentions_a_session_date(
    flashcard_prompt: str, study_plan_prompt: str, revision_prompt: str
) -> None:
    """`session_date` is checked first, so it must not appear in the other two."""
    assert CompliantStudyClient._SESSION.search(revision_prompt)
    assert not CompliantStudyClient._SESSION.search(flashcard_prompt)
    assert not CompliantStudyClient._SESSION.search(study_plan_prompt)


def test_only_the_flashcard_prompt_mentions_a_card_count(
    flashcard_prompt: str, study_plan_prompt: str, revision_prompt: str
) -> None:
    """`card_count` is checked before the plan's date pair."""
    assert CompliantStudyClient._COUNT.search(flashcard_prompt)
    assert not CompliantStudyClient._COUNT.search(study_plan_prompt)
    assert not CompliantStudyClient._COUNT.search(revision_prompt)


def test_the_double_answers_every_rendered_prompt(
    flashcard_prompt: str, study_plan_prompt: str, revision_prompt: str
) -> None:
    """End to end: the double raises AssertionError on a prompt it cannot place.

    The checks above pin each regex individually; this one proves the three
    prompts still route to three different branches.
    """
    client = CompliantStudyClient()

    for prompt in (flashcard_prompt, study_plan_prompt, revision_prompt):
        reply = client.create(messages=[{"role": "user", "content": prompt}])
        assert json.loads(reply.choices[0].message.content)


# --------------------------------------------------------------------------- #
# The shape reaches the model
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "fixture_name, required_key",
    [
        ("flashcard_prompt", "cards"),
        ("study_plan_prompt", "topic_schedule"),
        ("revision_prompt", "items"),
    ],
)
def test_the_prompt_shows_the_required_keys(
    fixture_name: str, required_key: str, request: pytest.FixtureRequest
) -> None:
    """Both belts: the literal example and the generated JSON schema."""
    prompt = request.getfixturevalue(fixture_name)

    assert required_key in prompt
    assert "needs_human_review" in prompt
    assert "JSON schema:" in prompt, "schema_block() is no longer appended"
