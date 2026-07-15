from src.agents.mentor_agent import MentorAgent
from src.validation.schemas import MentorOutput


def test_mentor_agent_generation():
    """
    Verify that the Mentor Agent generates
    a valid MentorOutput object.
    """

# ==========================================
# MOCK MODE
# Forces the agent to use the hardcoded
# mock response instead of calling LiteLLM.
# Use this while developing or when the
# API is unavailable.
# ==========================================
# agent = MentorAgent(mock_mode=True)  

# ==========================================
# REAL API MODE
# Forces the agent to call LiteLLM.
# This ignores the MOCK_MODE value in .env.
# Uncomment when the API is working.
# ==========================================
# agent = MentorAgent(mock_mode=False)


# ==========================================
# ENVIRONMENT MODE
# Uses the MOCK_MODE value from .env.
# If MOCK_MODE=true  -> uses mock response.
# If MOCK_MODE=false -> uses LiteLLM.
# ==========================================

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
    assert len(result.key_points) > 0
    assert len(result.next_steps) > 0
    assert len(result.references) > 0

    for reference in result.references:
        assert reference.segment_id
        assert reference.text