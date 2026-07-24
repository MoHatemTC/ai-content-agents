import pytest
from pydantic import ValidationError

from src.validation.schemas import (
    QuestionBankOutput,
    TestHelpOutput,
)


def test_question_bank_schema_requires_questions():

    invalid_data = {
        "requires_human_review": True
    }

    with pytest.raises(ValidationError):
        QuestionBankOutput.model_validate(invalid_data)


def test_test_help_schema_requires_questions():

    invalid_data = {
        "requires_human_review": True
    }

    with pytest.raises(ValidationError):
        TestHelpOutput.model_validate(invalid_data)


def test_question_bank_schema_accepts_valid_output():

    valid_data = {
        "questions": [
            {
                "question": "What is Python?",
                "options": [
                    "Language",
                    "Database",
                ],
                "correct_answer": "Language",
                "rationale": "Python is a programming language.",
                "difficulty": "beginner",
                "type": "mcq",
                "references": [
                    {
                        "segment_id": "seg1",
                        "text": "Python is a programming language."
                    }
                ],
            }
        ],
        "requires_human_review": True,
    }

    result = QuestionBankOutput.model_validate(valid_data)

    assert result.questions[0].question == "What is Python?"
    assert result.requires_human_review is True