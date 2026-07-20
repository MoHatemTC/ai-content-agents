"""
Pydantic output schemas for the Content Agents project.

These schemas define the structured JSON returned by AI agents.
They are shared across the application to ensure all generated
outputs follow a consistent format.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

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


class QuestionType(str, Enum):
    """
    Supported question types.
    """

    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class QuestionItem(BaseModel):
    """
    Represents a single generated question.

    This schema is shared by both the Question Bank
    and Test Help agents.
    """

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


class QuestionBankOutput(BaseModel):
    """
    Structured output schema for the Question Bank Agent.

    This agent generates a collection of grounded educational
    questions that require human review before use.
    """

    questions: list[QuestionItem] = Field(
        ...,
        description="List of generated questions."
    )

    requires_human_review: bool = Field(
        default=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented."
        )
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
        ...,
        description="List of generated questions."
    )

    requires_human_review: bool = Field(
        default=True,
        description=(
            "Indicates that the generated questions must be "
            "reviewed by a human before being presented."
        )
    )


class MentorOutput(BaseModel):
    """
    Structured output schema for the Mentor Agent.

    The Mentor Agent explains educational content while guiding
    learners with key takeaways and suggested next learning steps.
    """

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


class ConceptOutput(BaseModel):
    """
    Structured output schema for the Concept Explanation Agent.

    This agent focuses on explaining a concept clearly without
    providing mentoring or study guidance.
    """

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
    