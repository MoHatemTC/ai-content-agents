from unittest import result

from src.agents.question_bank_agent import QuestionBankAgent
from src.validation.schemas import QuestionBankOutput


def test_question_bank_generation():
    """
    Verify that the Question Bank Agent generates
    a valid QuestionBankOutput object.
    """

# ==========================================
# MOCK MODE
# Forces the agent to use the hardcoded
# mock response instead of calling LiteLLM.
# Use this while developing or when the
# API is unavailable.
# ==========================================
# agent = QuestionBankAgent(mock_mode=True)

# ==========================================
# REAL API MODE
# Forces the agent to call LiteLLM.
# This ignores the MOCK_MODE value in .env.
# Uncomment when the API is working.
# ==========================================
    agent = QuestionBankAgent(mock_mode=False)

# ==========================================
# ENVIRONMENT MODE
# Uses the MOCK_MODE value from .env.
# If MOCK_MODE=true  -> uses mock response.
# If MOCK_MODE=false -> uses LiteLLM.
# ==========================================

    # agent = QuestionBankAgent()

    result = agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
    )

    print("\n=== GENERATED OUTPUT ===")
    print(result.model_dump_json(indent=2))
    print("========================\n")

    print(result.model_dump_json(indent=2))

    assert isinstance(result, QuestionBankOutput)

    assert result.requires_human_review is True
    assert len(result.questions) > 0

    for question in result.questions:
        assert question.question
        assert question.correct_answer
        assert question.rationale
        assert question.difficulty
        assert question.type
        assert len(question.references) > 0

        if question.options is not None:
            assert len(question.options) > 0

        for reference in question.references:
            assert reference.segment_id
            assert reference.text