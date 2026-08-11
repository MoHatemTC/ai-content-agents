"""Pydantic schemas for the review milestone (M7).

Matches the contract defined in docs/FASTAPI_INTEGRATION.md and
Sensei-AI src/types/api/review.contracts.ts.
"""

from __future__ import annotations

from pydantic import BaseModel


class WsAuditEntry(BaseModel):
    id: str
    itemId: str
    itemLabel: str = ""
    action: str
    actor: str
    at: str
    comment: str | None = None


class ReviewRequest(BaseModel):
    workspaceId: str
    itemId: str
    comment: str | None = None
    label: str | None = None


class ReviewResponse(BaseModel):
    itemId: str
    status: str
    audit: WsAuditEntry


class GetReviewQueueResponse(BaseModel):
    itemIds: list[str]


class ReviewItem(BaseModel):
    """A persisted generated output, usable by the review UI (single source of truth).

    ``kind`` mirrors the agent's ``output_type`` (e.g. ``question_bank``) and
    ``items`` carries the human-reviewable content payload (e.g. the questions)
    so the frontend can render the review queue without trusting local state.
    """

    id: str
    kind: str
    status: str
    payload: dict[str, list | str]
    created_at: str


class GetReviewItemsResponse(BaseModel):
    items: list[ReviewItem]


class GetAuditHistoryResponse(BaseModel):
    audit: list[WsAuditEntry]
