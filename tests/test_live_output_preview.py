"""This developer-only test prints real LLM outputs for manual inspection. It is not intended for automated regression testing."""

import os
from pprint import pprint

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.validation.schemas import (
    ConceptOutput,
    MentorOutput,
    QuestionBankOutput,
    TestHelpOutput,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS", "").lower() != "true",
    reason="Set RUN_LIVE_TESTS=true to run live API tests.",
)


def test_live_output_preview():
    mentor_agent = MentorAgent()
    print("Model:", mentor_agent.model)
    mentor_result = mentor_agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        user_question="Explain loops.",
        difficulty="beginner",
    )
    print("=" * 50)
    print("MENTOR OUTPUT")
    print("=" * 50)
    pprint(mentor_result.model_dump())
    assert isinstance(mentor_result, MentorOutput)
    print("✓ Schema validated successfully")

    concept_agent = ConceptAgent()
    print("Model:", concept_agent.model)
    concept_result = concept_agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        user_question="What is a loop?",
        difficulty="beginner",
    )
    print("=" * 50)
    print("CONCEPT OUTPUT")
    print("=" * 50)
    pprint(concept_result.model_dump())
    assert isinstance(concept_result, ConceptOutput)
    print("✓ Schema validated successfully")

    question_bank_agent = QuestionBankAgent()
    print("Model:", question_bank_agent.model)
    question_bank_result = question_bank_agent.generate(
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
    print("=" * 50)
    print("QUESTION BANK OUTPUT")
    print("=" * 50)
    pprint(question_bank_result.model_dump())
    assert isinstance(question_bank_result, QuestionBankOutput)
    print("✓ Schema validated successfully")

    test_help_agent = TestHelpAgent()
    print("Model:", test_help_agent.model)
    test_help_result = test_help_agent.generate(
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
    print("=" * 50)
    print("TEST HELP OUTPUT")
    print("=" * 50)
    pprint(test_help_result.model_dump())
    assert isinstance(test_help_result, TestHelpOutput)
    print("✓ Schema validated successfully")
