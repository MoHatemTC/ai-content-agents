"""
Formatting helpers for Question Bank and Test Help outputs.

These helpers convert validated Pydantic models into plain
Python dictionaries for downstream consumers such as the UI
or API responses.
"""

from src.validation.schemas import (
    QuestionBankOutput,
    TestHelpOutput,
)


def format_question_bank(
    output: QuestionBankOutput,
) -> dict:
    """
    Format a QuestionBankOutput object.

    Args:
        output:
            Validated Question Bank output.

    Returns:
        Dictionary representation of the output.
    """

    return output.model_dump()


def format_test_help(
    output: TestHelpOutput,
) -> dict:
    """
    Format a TestHelpOutput object.

    Args:
        output:
            Validated Test Help output.

    Returns:
        Dictionary representation of the output.
    """

    return output.model_dump()