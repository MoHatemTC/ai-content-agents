"""Service layer for export endpoints (M8).

Reuses src/exports/export.py export_outputs, export_output, export_approved_run.
Enforces the human-review export gate (assert_exportable) server-side.
"""

from __future__ import annotations

import logging

from backend.errors import ApiError
from backend.exports.schemas import ExportRecord, ExportRequest, GetExportsResponse
from src.exports.export import (
    ExportFormat,
    export_approved_run,
    export_output,
    export_outputs,
)
from src.validation.review_schema import ExportBlockedError, OutputStatus
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


def export_approved_content_service(
    request: ExportRequest,
    *,
    db_path: str,
) -> tuple[bytes, str, str]:
    """Render approved outputs in the requested format.

    Returns (bytes_data, media_type, filename).
    Raises AppError 403 if content is not approved.
    """
    store = PlatformStore(db_path)
    fmt = ExportFormat(request.format)

    try:
        if request.output_id:
            output = store.get_output(request.output_id)
            if not output:
                raise ApiError(
                    status_code=404,
                    code="not_found",
                    message=f"Output {request.output_id} not found",
                )
            data = export_output(output, fmt, store=store)
            filename = f"export-{request.output_id}.{fmt.extension}"
        elif request.run_id:
            data = export_approved_run(
                request.run_id, fmt, store=store, title=request.title
            )
            filename = f"export-run-{request.run_id}.{fmt.extension}"
        else:
            outputs = store.list_outputs(status=OutputStatus.APPROVED)
            if request.workspaceId:
                filtered = []
                for out in outputs:
                    run = store.get_agent_run(out.agent_run_id)
                    if not run or f"workspace:{request.workspaceId}" in (
                        run.input_context or ""
                    ):
                        filtered.append(out)
                outputs = filtered
            data = export_outputs(outputs, fmt, title=request.title, store=store)
            filename = f"export-workspace.{fmt.extension}"

        return data, fmt.media_type, filename

    except ExportBlockedError as exc:
        raise ApiError(
            status_code=403,
            code="not_exportable",
            message=f"Export blocked: output {exc.output_id} is in status '{exc.status.value}', not 'approved'.",
        ) from exc


def list_exports_service(
    workspace_id: str,
    *,
    db_path: str,
) -> GetExportsResponse:
    """List completed export events for a workspace."""
    store = PlatformStore(db_path)
    events = store.list_events(event_type="EXPORT_COMPLETED")

    records: list[ExportRecord] = []
    for ev in events:
        records.append(
            ExportRecord(
                id=ev.id,
                run_id=ev.run_id,
                output_id=ev.output_id,
                format=ev.details.get("format", "json"),
                title=ev.message,
                created_at=ev.timestamp.isoformat(),
            )
        )

    return GetExportsResponse(exports=records)
