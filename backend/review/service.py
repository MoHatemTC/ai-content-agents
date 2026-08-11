"""Service layer for review endpoints (M7).

Authoritative server-side human review gate. Wraps PlatformStore,
apply_review, and log_event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.errors import ApiError
from backend.review.schemas import (
    GetAuditHistoryResponse,
    GetReviewItemsResponse,
    GetReviewQueueResponse,
    ReviewItem,
    ReviewRequest,
    ReviewResponse,
    WsAuditEntry,
)
from src.validation.review_schema import (
    IllegalTransitionError,
    OutputStatus,
    ReviewAction,
    apply_review,
)
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


def get_review_queue_service(
    workspace_id: str,
    *,
    db_path: str,
) -> GetReviewQueueResponse:
    """Return IDs of GeneratedOutputs pending review for a workspace."""
    store = PlatformStore(db_path)
    all_pending = store.list_outputs(status=OutputStatus.PENDING)

    item_ids: list[str] = []
    for output in all_pending:
        run = store.get_agent_run(output.agent_run_id)
        if run and f"workspace:{workspace_id}" in (run.input_context or ""):
            item_ids.append(output.id)
        elif not run or workspace_id in (run.input_context or ""):
            # Fallback when workspace matches
            item_ids.append(output.id)

    return GetReviewQueueResponse(itemIds=item_ids)


def get_review_items_service(
    workspace_id: str,
    *,
    db_path: str,
) -> GetReviewItemsResponse:
    """Return persisted generated outputs (with content) for a workspace.

    This is the authoritative, reload-safe view the review UI reads from: every
    item is the backend's ``generated_outputs`` row, so a decision made and then
    reloaded is still visible here (and everywhere ``apply_review`` persisted it).
    """
    store = PlatformStore(db_path)
    items: list[ReviewItem] = []
    for output in store.list_outputs():
        run = store.get_agent_run(output.agent_run_id)
        scoped = bool(run) and f"workspace:{workspace_id}" in (run.input_context or "")
        if not scoped:
            continue
        payload = output.payload or {}
        items.append(
            ReviewItem(
                id=output.id,
                kind=output.output_type,
                status=output.status.value,
                payload=payload,
                created_at=(
                    output.created_at.isoformat() if output.created_at else None
                )
                or "",
            )
        )
    items.sort(key=lambda i: i.created_at, reverse=True)
    return GetReviewItemsResponse(items=items)


def perform_review_action_service(
    request: ReviewRequest,
    action_type: str,
    *,
    reviewer_name: str,
    db_path: str,
) -> ReviewResponse:
    """Apply a review action (approve, reject, needs-edit, flag, comment) to an output item."""
    store = PlatformStore(db_path)
    output = store.get_output(request.itemId)

    if not output:
        raise KeyError(f"Generated output item {request.itemId} not found.")

    action_map = {
        "approve": ReviewAction.APPROVE,
        "reject": ReviewAction.REJECT,
        "needs-edit": ReviewAction.NEEDS_EDIT,
        "flag": ReviewAction.FLAG,
        "comment": ReviewAction.COMMENT,
    }

    action_enum = action_map.get(action_type.lower(), ReviewAction.COMMENT)
    try:
        review_rec = apply_review(
            output,
            reviewer=reviewer_name,
            action=action_enum,
            notes=request.comment or "",
        )
    except IllegalTransitionError as exc:
        raise ApiError(
            status_code=409,
            code="illegal_transition",
            message=f"Cannot '{action_enum.value}' item in status '{output.status.value}'. {exc}",
        ) from exc

    store.save_output(output)
    store.save_review(review_rec)

    at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    audit_entry = WsAuditEntry(
        id=review_rec.id,
        itemId=output.id,
        itemLabel=request.label or output.output_type.replace("_", " ").title(),
        action=action_enum.value,
        actor=reviewer_name,
        at=at_str,
        comment=request.comment,
    )

    store.log_event(
        "REVIEW_ACTION",
        f"Item {output.id} updated by {reviewer_name}: {action_enum.value}",
        output_id=output.id,
        details={
            "action": action_enum.value,
            "status": output.status.value,
            "actor": reviewer_name,
        },
    )

    return ReviewResponse(
        itemId=output.id,
        status=output.status.value,
        audit=audit_entry,
    )


def get_audit_history_service(
    workspace_id: str,
    *,
    db_path: str,
) -> GetAuditHistoryResponse:
    """Get audit trail of reviews for a workspace."""
    store = PlatformStore(db_path)
    reviews = store.list_reviews()

    audit_list: list[WsAuditEntry] = []
    for r in reversed(reviews):
        output = store.get_output(r.output_id)
        label = (
            output.output_type.replace("_", " ").title() if output else "Study Content"
        )
        audit_list.append(
            WsAuditEntry(
                id=r.id,
                itemId=r.output_id,
                itemLabel=label,
                action=r.action.value,
                actor=r.reviewer,
                at=r.timestamp.strftime("%Y-%m-%d %H:%M"),
                comment=r.notes,
            )
        )

    return GetAuditHistoryResponse(audit=audit_list)
