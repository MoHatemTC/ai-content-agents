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


class GetAuditHistoryResponse(BaseModel):
    audit: list[WsAuditEntry]
