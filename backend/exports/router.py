"""FastAPI router for export endpoints (M8).

Exposes POST /exports and GET /exports.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from backend.auth.schemas import AuthUser
from backend.config import Settings
from backend.deps import get_current_user, get_settings, require_workspace_member
from backend.exports.schemas import ExportRequest, GetExportsResponse
from backend.exports.service import (
    export_approved_content_service,
    list_exports_service,
)

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("")
async def export_content(
    request_body: ExportRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Export approved study outputs in JSON, CSV, Markdown, or PDF format."""
    if request_body.workspaceId:
        require_workspace_member(
            db_path=settings.platform_db_path,
            workspace_id=request_body.workspaceId,
            user=current_user,
        )
    data, media_type, filename = export_approved_content_service(
        request_body,
        db_path=settings.platform_db_path,
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=GetExportsResponse)
async def list_exports(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetExportsResponse:
    """List completed export history records for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return list_exports_service(workspace_id, db_path=settings.platform_db_path)
