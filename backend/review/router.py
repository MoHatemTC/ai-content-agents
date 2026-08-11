"""FastAPI router for review endpoints (M7).

Exposes GET /review, POST /review/approve, /review/reject, /review/needs-edit,
/review/flag, /review/comment, GET /review/audit.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.auth.schemas import AuthUser
from backend.config import Settings
from backend.deps import get_current_user, get_settings, require_workspace_member
from backend.review.schemas import (
    GetAuditHistoryResponse,
    GetReviewItemsResponse,
    GetReviewQueueResponse,
    ReviewRequest,
    ReviewResponse,
)
from backend.review.service import (
    get_audit_history_service,
    get_review_items_service,
    get_review_queue_service,
    perform_review_action_service,
)

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_model=GetReviewQueueResponse)
async def get_review_queue(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetReviewQueueResponse:
    """Get item IDs pending review for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return get_review_queue_service(workspace_id, db_path=settings.platform_db_path)


@router.get("/items", response_model=GetReviewItemsResponse)
async def get_review_items(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetReviewItemsResponse:
    """Get persisted generated outputs (with content) for a workspace.

    This is the reload-safe source of truth for the review UI: it returns the
    full items (not just ids), including items whose review decision was made
    in a previous session.
    """
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return get_review_items_service(workspace_id, db_path=settings.platform_db_path)


@router.post("/approve", response_model=ReviewResponse)
async def approve_item(
    request_body: ReviewRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    """Approve a generated output item."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return perform_review_action_service(
        request_body,
        action_type="approve",
        reviewer_name=current_user.name,
        db_path=settings.platform_db_path,
    )


@router.post("/reject", response_model=ReviewResponse)
async def reject_item(
    request_body: ReviewRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    """Reject a generated output item."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return perform_review_action_service(
        request_body,
        action_type="reject",
        reviewer_name=current_user.name,
        db_path=settings.platform_db_path,
    )


@router.post("/needs-edit", response_model=ReviewResponse)
async def request_edits_item(
    request_body: ReviewRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    """Mark a generated output item as needing edits."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return perform_review_action_service(
        request_body,
        action_type="needs-edit",
        reviewer_name=current_user.name,
        db_path=settings.platform_db_path,
    )


@router.post("/flag", response_model=ReviewResponse)
async def flag_item(
    request_body: ReviewRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    """Flag a generated output item for review."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return perform_review_action_service(
        request_body,
        action_type="flag",
        reviewer_name=current_user.name,
        db_path=settings.platform_db_path,
    )


@router.post("/comment", response_model=ReviewResponse)
async def comment_item(
    request_body: ReviewRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    """Add a review comment to an item without changing status."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return perform_review_action_service(
        request_body,
        action_type="comment",
        reviewer_name=current_user.name,
        db_path=settings.platform_db_path,
    )


@router.get("/audit", response_model=GetAuditHistoryResponse)
async def get_audit_history(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetAuditHistoryResponse:
    """Get audit trail of review actions for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return get_audit_history_service(workspace_id, db_path=settings.platform_db_path)
