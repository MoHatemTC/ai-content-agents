"""Pydantic schemas for the export milestone (M8).

Matches the contract defined in docs/FASTAPI_INTEGRATION.md and
Sensei-AI specs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    workspaceId: str | None = None
    output_id: str | None = None
    run_id: str | None = None
    format: Literal["json", "csv", "markdown", "pdf"] = "json"
    title: str = "Approved Study Content"


class ExportRecord(BaseModel):
    id: str
    run_id: str | None = None
    output_id: str | None = None
    format: str
    title: str
    created_at: str


class GetExportsResponse(BaseModel):
    exports: list[ExportRecord] = Field(default_factory=list)
