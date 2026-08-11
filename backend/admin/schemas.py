"""Pydantic schemas for the admin analytics milestone.

Matches the contract in Sensei-AI src/types/api/admin.contracts.ts.
"""

from __future__ import annotations

from pydantic import BaseModel


class AdminRecentDocument(BaseModel):
    """A document row shown in the admin library snapshot."""

    id: str
    title: str
    kind: str
    pages: int | None = None
    chunks: int
    status: str


class AdminStatsResponse(BaseModel):
    """Live site-wide totals computed from the platform database."""

    documents: int
    chunks_indexed: int
    workspaces: int
    users: int
    questions: int
    flashcards: int
    study_plans: int
    quality: float | None
    recent_documents: list[AdminRecentDocument]
