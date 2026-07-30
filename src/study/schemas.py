"""Extended Pydantic schemas for the Sprint 3 Study Agents lane.

These models extend the shared :mod:`src.schemas` contracts with the
grounding-aware and human-review-friendly fields required by the flashcard,
study-plan and revision agents. All fields use PEP 604 union syntax and
Google-style docstrings for consistency with the repository style.

The core design rule: every generated artifact carries a list of
``source_topics`` (extracted *only* from content, never invented) plus an
optional ``source_chunk_ids`` list tying it back to ingestion output, so the
groundedness verifier in :mod:`src.study.evaluation` can audit the output
without ever trusting the LLM alone.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Flashcard schema
# ---------------------------------------------------------------------------



class TopicSchedule(BaseModel):
    """A single topic entry in a study plan.

    ``topic`` is always validated against the real content-topic allow-list
    by :class:`StudyPlanAgent` before the plan is returned.
    """

    topic: str
    start_date: date
    end_date: date
    duration_hours: float
    difficulty: str = Field(
        "medium", description="Per-topic difficulty: easy/medium/hard."
    )
    resources: list[str] = Field(default_factory=list)


class StudyPlan(BaseModel):
    """A grounded, validated, human-review-ready study plan."""

    goal: str
    start_date: date
    end_date: date
    overall_difficulty: str = Field(
        "medium", description="Planner-level difficulty."
    )
    available_hours_per_week: float | None = Field(
        None, description="Learner's weekly study budget."
    )
    topic_schedule: list[TopicSchedule]
    source_topics: list[str] = Field(
        default_factory=list,
        description="Real content topics the plan schedules (subset of allow-list).",
    )
    needs_human_review: bool = Field(
        True, description="Gate flag: plans are pending review, never final."
    )


# ---------------------------------------------------------------------------
# Revision schema
# ---------------------------------------------------------------------------


class RevisionItem(BaseModel):
    """A single targeted revision item.

    ``topic`` is always validated against real content topics by
    :class:`RevisionAgent` before the item is returned.
    """

    topic: str
    description: str | None = None
    next_revision_date: date
    difficulty: str = Field(..., description="easy/medium/hard.")
    confidence_prompt: str | None = Field(
        None, description="Optional self-check prompt for this item."
    )
    source_chunk_id: str | None = None


class RevisionSession(BaseModel):
    """A grounded, validated, human-review-ready revision session."""

    session_date: date
    items: list[RevisionItem]
    notes: str | None = None
    selected_weak_topics: list[str] = Field(
        default_factory=list,
        description="Weak/selected topics this session targets (real content topics).",
    )
    source_topics: list[str] = Field(default_factory=list)
    needs_human_review: bool = Field(
        True, description="Gate flag: revision items are pending review, never final."
    )
