"""Application-facing reviewable generation for Mentor and Concept agents."""

from __future__ import annotations

from typing import Optional

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import GroundedContext
from src.validation.review_schema import GeneratedOutput


class MentorConceptService:
    """Route Mentor and Concept generation through the human-review gate."""

    def __init__(self, mock_mode: Optional[bool] = None) -> None:
        """Initialize the Mentor and Concept agents used by this service."""
        self.mentor_agent = MentorAgent(mock_mode=mock_mode)
        self.concept_agent = ConceptAgent(mock_mode=mock_mode)

    def generate_mentor_reviewable(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate a Mentor response as a pending review record."""
        return self.mentor_agent.generate_reviewable(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
            context=context,
        )

    def generate_concept_reviewable(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate a Concept response as a pending review record."""
        return self.concept_agent.generate_reviewable(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
            context=context,
        )
