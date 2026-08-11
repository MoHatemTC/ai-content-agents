import os

import pytest

from src.agents.mentor_agent import MentorAgent
from src.validation.schemas import MentorOutput

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS", "").lower() != "true",
    reason="Set RUN_LIVE_TESTS=true to run live API tests.",
)


def test_mentor_agent_generation_live():
    """Verify Mentor Agent generation against the live LLM."""
    agent = MentorAgent()

    result = agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        user_question="Explain loops.",
        difficulty="beginner",
    )

    assert isinstance(result, MentorOutput)
    assert result.explanation
    assert result.key_points
    assert result.next_steps
    assert result.references
