from src.services.formatters import (
    format_question_bank,
    format_test_help,
)
from src.validation.schemas import (
    ContentReference,
    DifficultyLevel,
    QuestionBankOutput,
    QuestionItem,
    QuestionType,
    TestHelpOutput,
)


def _question() -> QuestionItem:
    """One schema-valid question.

    These tests used `questions=[]`, which the schema now rejects: a request
    for questions that produces none is a failure, not an empty success
    (BUG-06). A populated item exercises the formatter better anyway - an
    empty list never reached the per-question rendering at all.
    """
    return QuestionItem(
        question="Which loop repeats while a condition is true?",
        options=["for", "while"],
        correct_answer="while",
        rationale="A while loop repeats while its condition is true.",
        difficulty=DifficultyLevel.BEGINNER,
        type=QuestionType.MCQ,
        references=[ContentReference(segment_id="chunk_001", text="Loops repeat.")],
    )


def test_format_question_bank():
    output = QuestionBankOutput(
        questions=[_question()],
        requires_human_review=True,
    )

    result = format_question_bank(output)

    assert isinstance(result, dict)
    assert "questions" in result
    assert "requires_human_review" in result


def test_format_test_help():
    output = TestHelpOutput(
        questions=[_question()],
        requires_human_review=True,
    )

    result = format_test_help(output)

    assert isinstance(result, dict)
    assert "questions" in result
    assert "requires_human_review" in result
