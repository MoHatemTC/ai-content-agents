"""Application-facing reviewable generation for Mentor and Concept agents."""

from __future__ import annotations

from typing import Any

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import GroundedContext
from src.validation.review_schema import GeneratedOutput


class MentorConceptService:
    """Route Mentor and Concept generation through the human-review gate."""

    def __init__(self, *, client: Any | None = None) -> None:
        """Initialize the Mentor and Concept agents used by this service.

        Args:
            client: An OpenAI-compatible client shared by both agents.
                Defaults to one built from the configured gateway; tests
                inject a double.
        """
        self.mentor_agent = MentorAgent(client=client)
        self.concept_agent = ConceptAgent(client=client)

    def generate_mentor_reviewable(
        self,
        content: str,
        user_question: str | None = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
        store: Any | None = None,
    ) -> GeneratedOutput:
        """Generate a Mentor response as a pending review record."""
        return self.mentor_agent.generate_reviewable(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
            context=context,
            store=store,
        )

    def generate_concept_reviewable(
        self,
        content: str,
        user_question: str | None = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
        store: Any | None = None,
    ) -> GeneratedOutput:
        """Generate a Concept response as a pending review record."""
        return self.concept_agent.generate_reviewable(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
            context=context,
            store=store,
        )
