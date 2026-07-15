"""
Pydantic output schemas for the Content Agents project.

These schemas define the structured JSON returned by AI agents.
They are shared across the application to ensure all generated
outputs follow a consistent format.
"""

from pydantic import BaseModel, Field

class ContentReference(BaseModel):
    segment_id: str
    text: str

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