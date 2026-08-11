"""End-to-end control round-trip for the Test Help agent.

The sibling of ``test_question_bank``; see that file for what was removed and
why. Kept separate because the two agents render different prompts, and the
whole point is that both do it correctly.
"""

import pytest

from src.agents.test_help_agent import TestHelpAgent
from tests.conftest import CompliantAgentsClient

CONTENT = """
Python provides two loop types: for and while.
A for loop is commonly used when the number of
iterations is known in advance.
A while loop continues until its condition
becomes false.
"""


@pytest.mark.parametrize("num_questions", [1, 3])
@pytest.mark.parametrize("question_type", ["mcq", "true_false"])
@pytest.mark.parametrize("difficulty", ["beginner", "advanced"])
def test_every_control_reaches_the_prompt(num_questions, question_type, difficulty):
    agent = TestHelpAgent(client=CompliantAgentsClient())

    result = agent.generate(
        content=CONTENT,
        question_type=question_type,
        difficulty=difficulty,
        num_questions=num_questions,
    )

    assert len(result.questions) == num_questions
    assert {q.type for q in result.questions} == {question_type}
    assert {q.difficulty for q in result.questions} == {difficulty}


def test_the_content_is_what_gets_cited():
    agent = TestHelpAgent(client=CompliantAgentsClient())

    result = agent.generate(
        content=CONTENT, question_type="mcq", difficulty="beginner", num_questions=1
    )

    (reference,) = result.questions[0].references
    assert reference.text.strip() in CONTENT.strip()
