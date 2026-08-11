"""What the output schemas accept and refuse."""

import pytest
from pydantic import ValidationError

from src.schemas import FlashcardSet
from src.study.schemas import RevisionSession, StudyPlan
from src.validation.schemas import (
    ConceptOutput,
    ContentReference,
    MentorOutput,
    QuestionBankOutput,
    QuestionItem,
    QuestionType,
    TestHelpOutput,
    validate_question_type,
)

A_CARD = {"front": "What is Python?", "back": "A programming language."}

A_FLASHCARD_SET = {"title": "Python", "cards": [A_CARD]}

A_STUDY_PLAN = {
    "goal": "Learn Python",
    "start_date": "2026-01-01",
    "end_date": "2026-01-28",
    "topic_schedule": [
        {
            "topic": "Loops",
            "start_date": "2026-01-01",
            "end_date": "2026-01-07",
            "duration_hours": 4.0,
        }
    ],
}

A_REVISION_SESSION = {
    "session_date": "2026-01-01",
    "items": [
        {
            "topic": "Loops",
            "next_revision_date": "2026-01-04",
            "difficulty": "medium",
        }
    ],
}

A_QUESTION = {
    "question": "What is Python?",
    "options": ["Language", "Database"],
    "correct_answer": "Language",
    "rationale": "Python is a programming language.",
    "difficulty": "beginner",
    "type": "mcq",
    "references": [
        {"segment_id": "seg1", "text": "Python is a programming language."}
    ],
}


@pytest.mark.parametrize("schema", [QuestionBankOutput, TestHelpOutput])
def test_a_question_set_with_no_questions_is_refused(schema):
    """An agent asked for questions that returns none has failed, not
    succeeded with an empty result."""
    with pytest.raises(ValidationError):
        schema.model_validate({"requires_human_review": True})


@pytest.mark.parametrize("schema", [QuestionBankOutput, TestHelpOutput])
def test_a_valid_question_set_is_accepted(schema):
    """Control: a schema that refused everything would pass the test above."""
    result = schema.model_validate(
        {"questions": [A_QUESTION], "requires_human_review": True}
    )

    assert result.questions[0].question == "What is Python?"
    assert result.questions[0].correct_answer == "Language"


# --------------------------------------------------------------------------- #
# extra="forbid"
# --------------------------------------------------------------------------- #


def test_a_near_miss_on_an_optional_field_is_refused():
    """The case that motivates forbidding extras.

    ``options`` is optional, so a reply carrying ``option`` used to be dropped
    in silence and validate cleanly - producing a multiple-choice question with
    no choices, which then went to a learner. Nothing in the pipeline could
    notice: the field the model *meant* to send simply was not there.
    """
    typo = {**A_QUESTION, "option": A_QUESTION["options"]}
    del typo["options"]

    with pytest.raises(ValidationError, match="option"):
        QuestionItem.model_validate(typo)


@pytest.mark.parametrize(
    "schema,payload",
    [
        (ContentReference, {"segment_id": "seg1", "text": "t"}),
        (
            MentorOutput,
            {
                "explanation": "e",
                "key_points": ["k"],
                "next_steps": ["n"],
                "references": [{"segment_id": "seg1", "text": "t"}],
                "requires_human_review": True,
            },
        ),
        (
            ConceptOutput,
            {
                "definition": "d",
                "explanation": "e",
                "key_points": ["k"],
                "references": [{"segment_id": "seg1", "text": "t"}],
                "requires_human_review": True,
            },
        ),
        (QuestionBankOutput, {"questions": [A_QUESTION], "requires_human_review": True}),
        (TestHelpOutput, {"questions": [A_QUESTION], "requires_human_review": True}),
        # The study three were left out of this list, which is exactly why they
        # kept accepting extras long after the content agents stopped.
        (FlashcardSet, A_FLASHCARD_SET),
        (StudyPlan, A_STUDY_PLAN),
        (RevisionSession, A_REVISION_SESSION),
    ],
    ids=[
        "reference",
        "mentor",
        "concept",
        "question_bank",
        "test_help",
        "flashcards",
        "study_plan",
        "revision",
    ],
)
def test_every_output_schema_forbids_unknown_fields(schema, payload):
    """All four prompts end with "do not add extra fields" and nothing enforced
    it - pydantic ignores unknown keys by default."""
    schema.model_validate(payload)  # the control: the payload itself is valid

    with pytest.raises(ValidationError, match="[Ee]xtra"):
        schema.model_validate({**payload, "confidence": 0.9})


def test_mentor_and_concept_do_not_accept_each_others_fields():
    """One shared payload used to satisfy both, which is how a test double came
    to send ``definition`` and ``next_steps`` together."""
    with pytest.raises(ValidationError, match="definition"):
        MentorOutput.model_validate(
            {
                "explanation": "e",
                "key_points": ["k"],
                "next_steps": ["n"],
                "definition": "d",
                "references": [{"segment_id": "seg1", "text": "t"}],
                "requires_human_review": True,
            }
        )


# --------------------------------------------------------------------------- #
# The study schemas, held to the same contract as the content ones
#
# Every rule below had been true of MentorOutput and QuestionBankOutput since
# #39 and was simply never applied here - and the parametrisation above, which
# is what would have caught it, listed only the content schemas.
# --------------------------------------------------------------------------- #


STUDY_SCHEMAS = [
    pytest.param(FlashcardSet, A_FLASHCARD_SET, "cards", id="flashcards"),
    pytest.param(StudyPlan, A_STUDY_PLAN, "topic_schedule", id="study_plan"),
    pytest.param(RevisionSession, A_REVISION_SESSION, "items", id="revision"),
]


@pytest.mark.parametrize("schema,payload,collection", STUDY_SCHEMAS)
def test_a_study_output_cannot_switch_off_its_own_review(schema, payload, collection):
    """The flag is a control over the system, not an output of it.

    It was a plain mutable bool defaulting True, so a reply carrying false was
    accepted verbatim.
    """
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, "needs_human_review": False})


@pytest.mark.parametrize("schema,payload,collection", STUDY_SCHEMAS)
def test_the_study_review_flag_cannot_be_flipped_after_the_fact(
    schema, payload, collection
):
    """Frozen, so no later caller can mark the output final either."""
    output = schema.model_validate(payload)

    with pytest.raises(ValidationError):
        output.needs_human_review = False


@pytest.mark.parametrize("schema,payload,collection", STUDY_SCHEMAS)
def test_an_empty_study_output_is_refused(schema, payload, collection):
    """A generation that produces nothing has failed, not succeeded.

    QuestionBankOutput has refused this since BUG-06; these three accepted it.
    """
    with pytest.raises(ValidationError, match="at least 1"):
        schema.model_validate({**payload, collection: []})


# --------------------------------------------------------------------------- #
# Question types arrive spelled the way humans and UIs write them
#
# The FastAPI layer passes the UI's display labels straight through - "MCQ",
# "True/False", "Short Answer" - and a strict enum lookup turned each of them
# into a 500 on a request that was entirely valid. Models do the same thing,
# answering "short answer" where the schema says "short_answer".
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written,expected",
    [
        ("MCQ", "mcq"),
        ("mcq", "mcq"),
        ("Multiple Choice", "mcq"),
        ("True/False", "true_false"),
        ("true-false", "true_false"),
        ("TRUE_FALSE", "true_false"),
        ("Short Answer", "short_answer"),
        ("short-answer", "short_answer"),
        ("short", "short_answer"),
    ],
)
def test_a_question_type_is_recognised_however_it_is_spelled(written, expected):
    assert validate_question_type(written).value == expected


@pytest.mark.parametrize("nonsense", ["ESSAY_BANANA", "essay", "", "multiple choices"])
def test_an_unsupported_question_type_is_still_refused(nonsense):
    """BUG-02's guarantee. Spelling is normalised; membership is not relaxed.

    Without this the alias table would be a way to smuggle anything through,
    which is the defect the strict lookup was added to close.
    """
    with pytest.raises(ValueError, match="Invalid question type"):
        validate_question_type(nonsense)


def test_an_enum_member_passes_through_unchanged():
    assert validate_question_type(QuestionType.MCQ) is QuestionType.MCQ
