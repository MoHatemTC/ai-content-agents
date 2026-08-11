"""
Pydantic output schemas for the Content Agents project.

These schemas define the structured JSON returned by AI agents.
They are shared across the application to ensure all generated
outputs follow a consistent format.
"""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

__test__ = False

# All four prompts end with "Do not add extra fields", and until now nothing
# enforced it: pydantic's default is to ignore unknown keys silently. The danger
# is not model creativity, it is a near-miss on an *optional* field - a reply
# carrying "option" instead of "options" was dropped without a word and produced
# a multiple-choice question with no choices, which then went to a learner.
# Forbidding extras turns that into a visible, retryable generation error.
_STRICT = ConfigDict(extra="forbid")


class ContentReference(BaseModel):
    """
    Reference to a retrieved content segment used for grounding.
    """

    model_config = _STRICT

    segment_id: str
    text: str


class DifficultyLevel(str, Enum):
    """
    Supported difficulty levels for generated questions.
    """

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


def validate_difficulty(value: str | DifficultyLevel) -> DifficultyLevel:
    """Validate and normalize a supported agent difficulty level."""
    try:
        return DifficultyLevel(value)
    except ValueError as exc:
        allowed = ", ".join(level.value for level in DifficultyLevel)
        raise ValueError(
            f"Invalid difficulty {value!r}; expected one of: {allowed}."
        ) from exc


class QuestionType(str, Enum):
    """
    Supported question types.
    """

    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


# How the same three types get written by everything that is not this enum.
# The UI labels them "MCQ", "True/False" and "Short Answer"; models answer with
# "short answer", "multiple choice", "true-false" and every casing of each.
# None of that is a caller asking for something unsupported - it is the same
# three types, spelled the way a human would.
_QUESTION_TYPE_ALIASES: dict[str, str] = {
    "mcq": "mcq",
    "multiple choice": "mcq",
    "true false": "true_false",
    "true or false": "true_false",
    "tf": "true_false",
    "boolean": "true_false",
    "short answer": "short_answer",
    "short": "short_answer",
}


def validate_question_type(value: str | QuestionType) -> QuestionType:
    """Validate and normalize a supported question type.

    The sibling of :func:`validate_difficulty`, which existed for a long time
    while nothing checked question types at all - so a caller could ask for
    ``"ESSAY_BANANA"`` and have it interpolated into the prompt verbatim
    (BUG-02).

    **Spelling is normalised; membership is not relaxed.** BUG-02's guarantee
    is that an unsupported type never reaches the prompt, and that still holds:
    ``"ESSAY_BANANA"`` raises exactly as before. What changes is that ``"MCQ"``
    no longer does. The FastAPI layer receives the UI's display labels - "MCQ",
    "True/False", "Short Answer" - and a strict enum lookup turned every one of
    them into a 500 on a request that was perfectly valid.
    """
    if isinstance(value, QuestionType):
        return value

    collapsed = " ".join(
        str(value).strip().lower().replace("_", " ").replace("-", " ").replace("/", " ").split()
    )
    canonical = _QUESTION_TYPE_ALIASES.get(collapsed, str(value))

    try:
        return QuestionType(canonical)
    except ValueError as exc:
        allowed = ", ".join(kind.value for kind in QuestionType)
        raise ValueError(
            f"Invalid question type {value!r}; expected one of: {allowed}."
        ) from exc


# Types where a question without choices is unanswerable. short_answer is
# deliberately absent: the prompts instruct the model to send null options for
# it (src/prompts/test_help.yaml).
_TYPES_REQUIRING_OPTIONS = frozenset({QuestionType.MCQ, QuestionType.TRUE_FALSE})


class QuestionItem(BaseModel):
    """
    Represents a single generated question.

    This schema is shared by both the Question Bank
    and Test Help agents.
    """

    model_config = _STRICT

    question: str = Field(
        ...,
        description="The generated question."
    )

    options: Optional[List[str]] = Field(
        default=None,
        description="Available answer choices for MCQ and True/False questions. Leave null for Short Answer questions."
    )

    correct_answer: str = Field(
        ...,
        description="Correct answer corresponding to the generated question."
    )

    rationale: str = Field(
        ...,
        description="Explanation of why the answer is correct."
    )

    difficulty: DifficultyLevel = Field(
        ...,
        description="Difficulty level of the question."
    )

    type: QuestionType = Field(
        ...,
        description="Type of the generated question."
    )

    references: list[ContentReference] = Field(
        ...,
        description="Grounding references used to generate the question."
    )

    @model_validator(mode="after")
    def _check_answerable(self) -> "QuestionItem":
        """Reject questions nobody could answer or score.

        These live in the schema rather than in an agent because the
        orchestrator validates through the schema and never calls the agents'
        ``generate()`` - a check placed there would not run in production.

        Raises:
            ValueError: If a choice-based question has no options, or the
                answer key is not one of the choices.
        """
        if self.type in _TYPES_REQUIRING_OPTIONS and not self.options:
            # A multiple-choice question with nothing to choose from (BUG-05).
            raise ValueError(
                f"a {self.type.value} question needs options; got "
                f"{self.options!r}"
            )

        if self.options and self.correct_answer not in self.options:
            # Unanswerable, and any scorer comparing a selection against the
            # key marks every attempt wrong (BUG-04).
            raise ValueError(
                f"correct_answer {self.correct_answer!r} is not one of the "
                f"options {self.options!r}"
            )

        return self


class QuestionBankOutput(BaseModel):
    """
    Structured output schema for the Question Bank Agent.

    This agent generates a collection of grounded educational
    questions that require human review before use.
    """

    model_config = _STRICT

    questions: list[QuestionItem] = Field(
        ...,
        min_length=1,
        description="List of generated questions. At least one - a request for "
                    "questions that produces none is a failure, not a success "
                    "(BUG-06)."
    )

    requires_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented. Literal and frozen, "
            "matching MentorOutput and ConceptOutput: this is a control over "
            "the system, so neither the model nor a later caller may switch it "
            "off (BUG-07)."
        )
    )


class TestHelpOutput(BaseModel):
    """
    Structured output schema for the Test Help Agent.

    This agent generates grounded questions for assessment
    support. All outputs require human review.
    """
    __test__ = False

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    questions: list[QuestionItem] = Field(
        ...,
        min_length=1,
        description="List of generated questions. At least one - a request for "
                    "questions that produces none is a failure, not a success "
                    "(BUG-06)."
    )

    requires_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented. Literal and frozen, "
            "matching MentorOutput and ConceptOutput: this is a control over "
            "the system, so neither the model nor a later caller may switch it "
            "off (BUG-07)."
        )
    )


class MentorOutput(BaseModel):
    """
    Structured output schema for the Mentor Agent.

    The Mentor Agent explains educational content while guiding
    learners with key takeaways and suggested next learning steps.
    """

    model_config = _STRICT

    explanation: str = Field(
        ...,
        description="Detailed explanation of the educational content."
    )

    key_points: list[str] = Field(
        ...,
        description="Important concepts or takeaways from the content."
    )

    next_steps: list[str] = Field(
        ...,
        description="Recommended actions or topics for the learner to study next."
    )

    references: list[ContentReference] = Field(
        ...,
        description="Content chunks or references used to generate the response."
    )

    requires_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description="Indicates that the response requires human review before use.",
    )


class ConceptOutput(BaseModel):
    """
    Structured output schema for the Concept Explanation Agent.

    This agent focuses on explaining a concept clearly without
    providing mentoring or study guidance.
    """

    model_config = _STRICT

    definition: str = Field(
        ...,
        description="Short definition of the requested concept."
    )

    explanation: str = Field(
        ...,
        description="Detailed explanation of the concept."
    )

    key_points: list[str] = Field(
        ...,
        description="Important points that summarize the concept."
    )

    references: list[ContentReference] = Field(
        ...,
        description="Content chunks or references used to generate the explanation."
    )

    requires_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description="Indicates that the explanation requires human review before use.",
    )
    
