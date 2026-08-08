"""FastAPI router for history endpoints (M7).

Exposes GET /history (list a workspace's generation runs) and POST /history
(record a generation run).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.auth.schemas import AuthUser
from backend.config import Settings
from backend.deps import get_current_user, get_settings, require_workspace_member
from backend.history.schemas import (
    AppendHistoryRequest,
    GetHistoryResponse,
    HistoryRow,
)
from backend.history.service import append_history_service, list_history_service

router = APIRouter(tags=["history"])


@router.get("/history", response_model=GetHistoryResponse)
async def list_history(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetHistoryResponse:
    """List generation-run history for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return list_history_service(
        workspace_id,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
    )


@router.post("/history", response_model=HistoryRow)
async def append_history(
    request_body: AppendHistoryRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HistoryRow:
    """Record a generation run in a workspace's history."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return append_history_service(
        request_body,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
    )
