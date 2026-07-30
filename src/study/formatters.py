"""Formatting helpers for the Sprint 3 study lane outputs.

These helpers convert validated Pydantic models (``FlashcardSet``,
``StudyPlan``, ``RevisionSession``) into plain Python dictionaries suitable
for the Streamlit UI, JSON APIs, or export flows downstream.

All helpers are pure: they do not touch state, they do not mutate the input,
and they return built-in types. Dates are serialised via ``isoformat()`` so
the resulting dict is JSON-safe.
"""

from __future__ import annotations

from typing import Any

from src.schemas import FlashcardSet
from src.study.schemas import RevisionSession, StudyPlan


def _json_safe(value: Any) -> Any:
    """Recursively render dates via isoformat and models via model_dump."""
    from datetime import date, datetime

    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def format_flashcard_set(card_set: FlashcardSet) -> dict[str, Any]:
    """Format a FlashcardSet into a JSON-safe plain dict.

    Args:
        card_set: Validated flashcard set.

    Returns:
        Plain dict with dates/values rendered as JSON-serialisable primitives.
    """
    data = card_set.model_dump(mode="python")
    return _json_safe(data)


def format_study_plan(plan: StudyPlan) -> dict[str, Any]:
    """Format a StudyPlan into a JSON-safe plain dict.

    Args:
        plan: Validated study plan.

    Returns:
        Plain dict with dates rendered as ISO strings.
    """
    return _json_safe(plan.model_dump(mode="python"))


def format_revision_session(session: RevisionSession) -> dict[str, Any]:
    """Format a RevisionSession into a JSON-safe plain dict.

    Args:
        session: Validated revision session.

    Returns:
        Plain dict with dates rendered as ISO strings.
    """
    return _json_safe(session.model_dump(mode="python"))
