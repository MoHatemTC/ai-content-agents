from src.services.formatters import (
    format_question_bank,
    format_test_help,
)

from src.validation.schemas import (
    QuestionBankOutput,
    TestHelpOutput,
)


def test_format_question_bank():
    output = QuestionBankOutput(
        questions=[],
        requires_human_review=True,
    )

    result = format_question_bank(output)

    assert isinstance(result, dict)
    assert "questions" in result
    assert "requires_human_review" in result


def test_format_test_help():
    output = TestHelpOutput(
        questions=[],
        requires_human_review=True,
    )

    result = format_test_help(output)

    assert isinstance(result, dict)
    assert "questions" in result
    assert "requires_human_review" in result