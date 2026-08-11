import os

import pytest

from src.agents.question_bank_agent import QuestionBankAgent
from src.validation.schemas import QuestionBankOutput

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS", "").lower() != "true",
    reason="Set RUN_LIVE_TESTS=true to run live API tests.",
)


def test_question_bank_generation_live():
    """
    Verify that the Question Bank Agent can generate
    a valid QuestionBankOutput using the live LLM.
    """

    agent = QuestionBankAgent()

    result = agent.generate(
        content="""
Python is a programming language.

A loop repeats instructions.

There are two loop types:
- for
- while
""",
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
    )

    assert isinstance(result, QuestionBankOutput)

    assert result.requires_human_review is True
    assert len(result.questions) == 1

    question = result.questions[0]

    assert question.question
    assert question.correct_answer
    assert question.options
    assert question.references
