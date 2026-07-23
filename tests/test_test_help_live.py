import os
import pytest

from src.agents.test_help_agent import TestHelpAgent
from src.validation.schemas import TestHelpOutput


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS", "").lower() != "true",
    reason="Set RUN_LIVE_TESTS=true to run live API tests.",
)


def test_test_help_generation_live():
    """
    Verify that the Test Help Agent can generate
    a valid TestHelpOutput using the live LLM.
    """

    agent = TestHelpAgent(mock_mode=False)

    result = agent.generate(
        content="""
Python provides two loop types:
for and while.

A for loop is commonly used when the
number of iterations is known.

A while loop continues until its
condition becomes false.
""",
        question_type="mcq",
        difficulty="beginner",
        num_questions=1,
    )

    print("\n=== LIVE GENERATED OUTPUT ===")
    print(result.model_dump_json(indent=2))
    print("=============================\n")

    assert isinstance(result, TestHelpOutput)

    assert result.requires_human_review is True
    assert len(result.questions) == 1

    question = result.questions[0]

    assert question.question
    assert question.correct_answer
    assert question.options
    assert question.references