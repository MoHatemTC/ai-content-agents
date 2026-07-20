from unittest import result

from src.agents.test_help_agent import TestHelpAgent
from src.validation.schemas import TestHelpOutput


def test_test_help_generation():
    """
    Verify that the Test Help Agent generates
    a valid TestHelpOutput object.
    """

# ==========================================
# MOCK MODE
# Forces the agent to use the hardcoded
# mock response instead of calling LiteLLM.
# Use this while developing or when the
# API is unavailable.
# ==========================================
# agent = TestHelpAgent(mock_mode=True)

# ==========================================
# REAL API MODE
# Forces the agent to call LiteLLM.
# This ignores the MOCK_MODE value in .env.
# Uncomment when the API is working.
# ==========================================
    agent = TestHelpAgent(mock_mode=False)

# ==========================================
# ENVIRONMENT MODE
# Uses the MOCK_MODE value from .env.
# If MOCK_MODE=true  -> uses mock response.
# If MOCK_MODE=false -> uses LiteLLM.
# ==========================================

    # agent = HelpAgent()
    
    result = agent.generate(
        content="""
Python provides two loop types: for and while.
A for loop is commonly used when the number of
iterations is known in advance.
A while loop continues until its condition
becomes false.
""",
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
    )

    print("\n=== GENERATED OUTPUT ===")
    print(result.model_dump_json(indent=2))
    print("========================\n")

    assert isinstance(result, TestHelpOutput)

    assert result.requires_human_review is True
    assert len(result.questions) == 1

    question = result.questions[0]

    assert question.question
    assert question.correct_answer
    assert question.rationale
    assert question.options is not None
    assert len(question.options) > 0
    assert question.references

    for reference in question.references:
        assert reference.segment_id
        assert reference.text