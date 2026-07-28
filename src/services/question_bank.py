"""Application-facing reviewable generation for Question Bank and Test Help."""

from __future__ import annotations

from typing import Optional

from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.retrieval.models import GroundedContext
from src.validation.review_schema import GeneratedOutput


class QuestionBankService:
    """Route question generation through the shared human-review gate."""

    def __init__(self, mock_mode: Optional[bool] = None) -> None:
        self.question_bank_agent = QuestionBankAgent(mock_mode=mock_mode)
        self.test_help_agent = TestHelpAgent(mock_mode=mock_mode)

    def generate_question_bank_reviewable(
        self,
        content: str,
        question_type: str = "mcq",
        difficulty: str = "beginner",
        num_questions: int = 1,
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate a Question Bank set as a pending review record."""
        return self.question_bank_agent.generate_reviewable(
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
            context=context,
        )

    def generate_test_help_reviewable(
        self,
        content: str,
        question_type: str = "mcq",
        difficulty: str = "beginner",
        num_questions: int = 1,
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate a Test Help set as a pending review record."""
        return self.test_help_agent.generate_reviewable(
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
            context=context,
        )
