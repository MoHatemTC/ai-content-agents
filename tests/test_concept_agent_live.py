import os

import pytest

from src.agents.concept_agent import ConceptAgent
from src.validation.schemas import ConceptOutput

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS", "").lower() != "true",
    reason="Set RUN_LIVE_TESTS=true to run live API tests.",
)


def test_concept_agent_generation_live():
    """Verify Concept Agent generation against the live LLM."""
    agent = ConceptAgent()

    result = agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        user_question="What is a loop?",
        difficulty="beginner",
    )

    assert isinstance(result, ConceptOutput)
    assert result.definition
    assert result.explanation
    assert result.key_points
    assert result.references
