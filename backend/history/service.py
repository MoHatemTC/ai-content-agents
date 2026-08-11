"""Service layer for history endpoints (M7).

Generation runs are recorded by the UI (POST /history) so the History page can
re-list them after a refresh; the rows are scoped to ``(workspace_id, user_id)``
exactly like chats.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.db import connect
from backend.history.schemas import (
    AppendHistoryRequest,
    GetHistoryResponse,
    HistoryRow,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_from_record(record: sqlite3.Row) -> HistoryRow:
    return HistoryRow(
        id=record["id"],
        date=record["date"],
        agent=record["agent"],
        doc=record["doc"],
        status=record["status"],
        quality=record["quality"],
        review=record["review"],
        items=record["items"],
        chatId=record["chat_id"],
    )


def list_history_service(
    workspace_id: str,
    *,
    user_id: str,
    db_path: str,
) -> GetHistoryResponse:
    """Return history rows for a workspace, newest first."""
    conn = connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT id, date, agent, doc, status, quality, review, items, chat_id
            FROM history
            WHERE workspace_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (workspace_id, user_id),
        ).fetchall()
        return GetHistoryResponse(history=[_row_from_record(r) for r in records])
    finally:
        conn.close()


def append_history_service(
    request: AppendHistoryRequest,
    *,
    user_id: str,
    db_path: str,
) -> HistoryRow:
    """Insert or update a history row (idempotent by row id)."""
    row = request.row
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO history (
                id, workspace_id, user_id, agent, doc, status, quality, review,
                items, chat_id, date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent = excluded.agent,
                doc = excluded.doc,
                status = excluded.status,
                quality = excluded.quality,
                review = excluded.review,
                items = excluded.items,
                chat_id = excluded.chat_id,
                date = excluded.date
            """,
            (
                row.id,
                request.workspaceId,
                user_id,
                row.agent,
                row.doc,
                row.status,
                row.quality,
                row.review,
                row.items,
                row.chatId,
                row.date,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return row
