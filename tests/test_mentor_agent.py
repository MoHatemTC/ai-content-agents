"""Unit tests for MentorAgent mock-mode generation."""

from src.agents.mentor_agent import MentorAgent
from src.validation.schemas import MentorOutput
from tests.conftest import CompliantAgentsClient


def test_mentor_agent_generation():
    """
    Verify that the Mentor Agent generates
    a valid MentorOutput object.
    """

    agent = MentorAgent(client=CompliantAgentsClient())

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
    assert len(result.key_points) > 0
    assert len(result.next_steps) > 0
    assert len(result.references) > 0

    for reference in result.references:
        assert reference.segment_id
        assert reference.text
