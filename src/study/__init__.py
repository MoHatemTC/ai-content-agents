"""Study Agents Lane (Sprint 3): Flashcards, Study Plan & Revision Assistant.

This self-contained lane owns the learner-facing study agents end-to-end. It
exposes three grounded, schema-validated agents whose outputs always route
through the shared human-review gate before they can be presented as final:

* :class:`FlashcardAgent`  - term-definition / Q-A cards from selected content.
* :class:`StudyPlanAgent`  - learner goal + difficulty + time bound plan.
* :class:`RevisionAgent`   - targeted revision items from weak/selected topics.

Supporting pieces:

* :mod:`src.study.formatters` - plain-dict rendering for UI/exports.
* :mod:`src.study.batch`      - batched generation across a demo dataset.
* :mod:`src.study.evaluation` - quality + groundedness benchmark harness.
* :mod:`src.study.ui`         - Streamlit demo page.
"""

from __future__ import annotations

from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_flashcard_set,
    format_revision_session,
    format_study_plan,
)
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent

__all__ = [
    "FlashcardAgent",
    "RevisionAgent",
    "StudyPlanAgent",
    "format_flashcard_set",
    "format_revision_session",
    "format_study_plan",
]
