"""
Pydantic output schemas for the Content Agents project.

These schemas define the structured JSON returned by AI agents.
They are shared across the application to ensure all generated
outputs follow a consistent format.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__test__ = False


class ContentReference(BaseModel):
    """
    Reference to a retrieved content segment used for grounding.
    """

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


def normalize_question_type(raw: object) -> str:
    """Map common LLM spellings of a question type to the canonical enum value.

    Real gateway responses are inconsistent ("short", "Short Answer",
    "short-answer", "MCQ", "true/false", ...) while the schema enum only
    accepts the canonical values. Normalising before validation turns a
    cosmetic abbreviation into a 500 into a working request.
    """
    if isinstance(raw, QuestionType):
        return raw.value
    value = " ".join(
        str(raw).strip().lower().replace("_", " ").replace("-", " ").replace("/", " ").split()
    )
    aliases: dict[str, str] = {
        "mcq": "mcq",
        "multiple choice": "mcq",
        "multiplechoice": "mcq",
        "true false": "true_false",
        "true or false": "true_false",
        "truefalse": "true_false",
        "tf": "true_false",
        "boolean": "true_false",
        "short answer": "short_answer",
        "shortanswer": "short_answer",
        "short": "short_answer",
    }
    return aliases.get(value, str(raw))


def normalize_question_payload(payload: dict) -> dict:
    """Rewrite every ``questions[].type`` to its canonical enum value.

    Returns a shallow-copied payload so the caller's dict is untouched.
    """
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return payload
    cleaned: list[dict] = []
    for question in questions:
        if not isinstance(question, dict):
            cleaned.append(question)
            continue
        cleaned.append({**question, "type": normalize_question_type(question.get("type"))})
    return {**payload, "questions": cleaned}


class QuestionItem(BaseModel):
    """
    Represents a single generated question.

    This schema is shared by both the Question Bank
    and Test Help agents.
    """

    question: str = Field(..., description="The generated question.")

    options: list[str] | None = Field(
        default=None,
        description="Available answer choices for MCQ and True/False questions. Leave null for Short Answer questions.",
    )

    correct_answer: str = Field(
        ..., description="Correct answer corresponding to the generated question."
    )

    rationale: str = Field(..., description="Explanation of why the answer is correct.")

    difficulty: DifficultyLevel = Field(
        ..., description="Difficulty level of the question."
    )

    type: QuestionType = Field(..., description="Type of the generated question.")

    references: list[ContentReference] = Field(
        ..., description="Grounding references used to generate the question."
    )


class QuestionBankOutput(BaseModel):
    """
    Structured output schema for the Question Bank Agent.

    This agent generates a collection of grounded educational
    questions that require human review before use.
    """

    questions: list[QuestionItem] = Field(
        ..., description="List of generated questions."
    )

    requires_human_review: bool = Field(
        default=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented."
        ),
    )


class TestHelpOutput(BaseModel):
    """
    Structured output schema for the Test Help Agent.

    This agent generates grounded questions for assessment
    support. All outputs require human review.
    """

    __test__ = False

    model_config = ConfigDict(protected_namespaces=())

    questions: list[QuestionItem] = Field(
        ..., description="List of generated questions."
    )

    requires_human_review: bool = Field(
        default=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented."
        ),
    )


class MentorOutput(BaseModel):
    """
    Structured output schema for the Mentor Agent.

    The Mentor Agent explains educational content while guiding
    learners with key takeaways and suggested next learning steps.
    """

    explanation: str = Field(
        ..., description="Detailed explanation of the educational content."
    )

    key_points: list[str] = Field(
        ..., description="Important concepts or takeaways from the content."
    )

    next_steps: list[str] = Field(
        ..., description="Recommended actions or topics for the learner to study next."
    )

    references: list[ContentReference] = Field(
        ..., description="Content chunks or references used to generate the response."
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

    definition: str = Field(
        ..., description="Short definition of the requested concept."
    )

    explanation: str = Field(..., description="Detailed explanation of the concept.")

    key_points: list[str] = Field(
        ..., description="Important points that summarize the concept."
    )

    references: list[ContentReference] = Field(
        ...,
        description="Content chunks or references used to generate the explanation.",
    )

    requires_human_review: Literal[True] = Field(
        default=True,
        frozen=True,
        description="Indicates that the explanation requires human review before use.",
    )
