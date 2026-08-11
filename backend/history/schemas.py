"""Pydantic schemas for the history endpoints (M7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryRow(BaseModel):
    """A single generation-run row rendered by the History page."""

    id: str
    date: str
    agent: str
    doc: str
    status: str
    quality: float = Field(default=0.0)
    review: str
    items: int = Field(default=0)
    chatId: str | None = None


class AppendHistoryRequest(BaseModel):
    """POST /history body: the workspace and the row to record."""

    workspaceId: str
    row: HistoryRow


class GetHistoryResponse(BaseModel):
    """GET /history response."""

    history: list[HistoryRow]
