"""Mentor and Concept are asked for depth, and given room to deliver it.

Measured from a real session before this: concept explanations ran 254-359
characters, mentor 720-843, one of each as short as 28. Nothing was truncating
them - the agents sent a flat 2,000-token cap and the replies used about 15% of
it. The prompts simply never asked for depth, and mentor.yaml went further and
asked for the opposite: "Keep explanations clear, concise, and educational."

So the fix is the prompt, and the budget is headroom for it. Both are pinned
here, along with the prohibitions that must survive: a depth request that
quietly licensed padding would be worse than the brevity it replaced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.agents.concept_agent import ConceptAgent
from src.agents.explanation_agent_base import EXPLANATION_TOKENS
from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient

PROMPTS = Path(__file__).resolve().parents[2] / "src" / "prompts"

AGENTS = [
    pytest.param(MentorAgent, "mentor.yaml", id="mentor"),
    pytest.param(ConceptAgent, "concept.yaml", id="concept"),
]

# The shape every prompt in the repo shares, established in #41.
EXPECTED_KEYS = [
    "name",
    "description",
    "role",
    "instructions",
    "output_schema",
    "notes",
    "prompt_template",
]


def load(filename: str) -> dict:
    return yaml.safe_load((PROMPTS / filename).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The prompt asks for depth
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_prompt_asks_for_depth(agent_class, filename) -> None:
    """The cause of the two-sentence answers, stated as a test.

    Before this, neither file contained the word "depth", "detail", "thorough"
    or "paragraph" anywhere.
    """
    data = load(filename)
    instructions = " ".join(data["instructions"]).lower()
    template = data["prompt_template"].lower()

    assert "in depth" in instructions
    assert "in depth" in template
    assert "paragraph" in instructions and "paragraph" in template


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_prompt_asks_for_real_key_points(agent_class, filename) -> None:
    """One-word bullets were a large part of what read as "not detailed"."""
    template = load(filename)["prompt_template"].lower()

    assert "3 to 5 key_points" in template
    assert "fragment" in template


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_example_must_come_from_the_passages(agent_class, filename) -> None:
    """Asking for a worked example is an invitation to invent one, unless said."""
    template = load(filename)["prompt_template"].lower()

    assert "never one you invented" in template


def test_the_mentor_prompt_no_longer_asks_for_brevity() -> None:
    """It literally instructed "concise", and the model complied."""
    instructions = " ".join(load("mentor.yaml")["instructions"]).lower()

    assert "concise" not in instructions


# --------------------------------------------------------------------------- #
# Depth must not become licence to pad
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_grounding_prohibitions_survive(agent_class, filename) -> None:
    """The whole change is additive. Every rule that was there stays there.

    A prompt that asks for several paragraphs and no longer says "state the
    limitation" would fill the space by inventing - trading a thin answer for
    a confident wrong one, which is the worse failure.
    """
    data = load(filename)
    everything = (" ".join(data["instructions"]) + data["prompt_template"]).lower()

    assert "do not hallucinate" in everything
    assert "brief only when the passages genuinely do not carry more" in everything
    assert "insufficient" in everything or "not contain enough" in everything


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_prompt_keeps_the_shared_shape(agent_class, filename) -> None:
    assert list(load(filename)) == EXPECTED_KEYS


# --------------------------------------------------------------------------- #
# Room to write it
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_class,filename", AGENTS)
def test_the_agent_sends_the_larger_budget(agent_class, filename) -> None:
    """Assert on what reached the gateway, not on the constant.

    The same trap as the question-budget fix: a constant can be right while the
    call site still sends something else.
    """
    client = CompliantAgentsClient()
    agent = agent_class(client=client, model="test-model")

    agent.generate("Vector spaces are closed under addition.", "What is a vector space?")

    assert client.calls[-1]["max_tokens"] == EXPLANATION_TOKENS


def test_the_budget_leaves_room_for_a_detailed_answer() -> None:
    """4,000 tokens is roughly 3,000 words, against a 254-843 char baseline."""
    assert EXPLANATION_TOKENS >= 4000
