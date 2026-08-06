"""Service layer for review endpoints (M7).

Authoritative server-side human review gate. Wraps PlatformStore,
apply_review, and log_event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.review.schemas import (
    GetAuditHistoryResponse,
    GetReviewQueueResponse,
    ReviewRequest,
    ReviewResponse,
    WsAuditEntry,
)
from src.validation.review_schema import (
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
    updated_output, review_rec = apply_review(
        output,
        reviewer=reviewer_name,
        action=action_enum,
        notes=request.comment or "",
    )

    store.save_output(updated_output)
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
            "status": updated_output.status.value,
            "actor": reviewer_name,
        },
    )

    return ReviewResponse(
        itemId=output.id,
        status=updated_output.status.value,
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
