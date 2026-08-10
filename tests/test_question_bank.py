"""End-to-end control round-trip for the Question Bank agent.

``CompliantAgentsClient`` parses the rendered prompt and answers from what it
finds there, so asserting on the controls proves the agent put them in the
prompt. What was dropped from this file: ``assert result.requires_human_review
is True`` (the field is ``Literal[True]`` - pydantic will not construct the
model with anything else, so the line cannot fail), truthiness checks on
required fields that the schema already enforces, and two ``print`` calls of
the same JSON.
"""

import pytest

from src.agents.question_bank_agent import QuestionBankAgent
from tests.conftest import CompliantAgentsClient

CONTENT = """
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
"""


@pytest.mark.parametrize("num_questions", [1, 3])
@pytest.mark.parametrize("question_type", ["mcq", "true_false"])
@pytest.mark.parametrize("difficulty", ["beginner", "advanced"])
def test_every_control_reaches_the_prompt(num_questions, question_type, difficulty):
    """A control the agent forgets to render is a control the model ignores."""
    agent = QuestionBankAgent(client=CompliantAgentsClient())

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
    """The reference text must come from the supplied passage, not be invented.

    The fake quotes back whatever the prompt gave it, so a reference that does
    not appear in CONTENT means the agent sent the model something else.
    """
    agent = QuestionBankAgent(client=CompliantAgentsClient())

    result = agent.generate(
        content=CONTENT, question_type="mcq", difficulty="beginner", num_questions=1
    )

    (reference,) = result.questions[0].references
    assert reference.text.strip() in CONTENT.strip()
