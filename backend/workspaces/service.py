"""Service functions for the workspaces domain (M2)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .schemas import Accent, Workspace

_ACCENTS: list[Accent] = ["primary", "info", "success", "warning"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def _accent_for(i: int) -> Accent:
    return _ACCENTS[i % len(_ACCENTS)]


def row_to_workspace(row: sqlite3.Row, docs: int = 0) -> Workspace:
    return Workspace(
        id=row["id"],
        name=row["name"],
        subject=row["subject"],
        description=row["description"],
        accent=row["accent"],
        docs=docs,
        assets=0,
        pendingReview=0,
    )


def _document_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Documents per workspace, so the read model's ``docs`` is real (M3)."""
    counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT workspace_id, COUNT(*) AS c FROM documents GROUP BY workspace_id"
    ):
        counts[row["workspace_id"]] = int(row["c"])
    return counts


def list_workspaces(conn: sqlite3.Connection, owner_id: str) -> list[Workspace]:
    rows = conn.execute(
        "SELECT * FROM workspaces WHERE owner_id = ? ORDER BY created_at",
        (owner_id,),
    ).fetchall()
    counts = _document_counts(conn)
    return [row_to_workspace(row, docs=counts.get(row["id"], 0)) for row in rows]


def get_workspace(conn: sqlite3.Connection, workspace_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
    ).fetchone()


def get_workspace_docs(conn: sqlite3.Connection, workspace_id: str) -> int:
    """Document count for one workspace, for the read model's ``docs`` field."""
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM documents WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    return int(row["c"])


def create_workspace(
    conn: sqlite3.Connection, owner_id: str, name: str, description: str | None
) -> tuple[Workspace, bool]:
    """Create a workspace. Returns (workspace, created) where ``created`` is
    False when a same-named workspace already exists for this owner."""
    existing = conn.execute(
        "SELECT id FROM workspaces WHERE owner_id = ? AND LOWER(name) = LOWER(?)",
        (owner_id, name),
    ).fetchone()
    if existing is not None:
        return Workspace(
            id=existing["id"],
            name=name,
            subject="",
            description=description,
            accent="primary",
        ), False

    workspace_id = str(uuid.uuid4())
    created_at = now().isoformat()
    accent = _accent_for(_next_accent_index(conn, owner_id))
    conn.execute(
        """
        INSERT INTO workspaces (id, owner_id, name, subject, description, accent, created_at, updated_at)
        VALUES (?, ?, ?, '', ?, ?, ?, ?)
        """,
        (workspace_id, owner_id, name, description, accent, created_at, created_at),
    )
    conn.commit()
    return Workspace(
        id=workspace_id,
        name=name,
        subject="",
        description=description,
        accent=accent,
    ), True


def _next_accent_index(conn: sqlite3.Connection, owner_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM workspaces WHERE owner_id = ?", (owner_id,)
    ).fetchone()
    return row["c"]


def update_workspace(
    conn: sqlite3.Connection, workspace_id: str, patch: dict
) -> sqlite3.Row | None:
    current = get_workspace(conn, workspace_id)
    if current is None:
        return None
    allowed = {"name", "description", "subject"}
    updates = {k: v for k, v in patch.items() if k in allowed}
    if not updates:
        return current
    updates["updated_at"] = now().isoformat()
    sets = ", ".join(f"{col} = ?" for col in updates)
    conn.execute(
        f"UPDATE workspaces SET {sets} WHERE id = ?",
        (*updates.values(), workspace_id),
    )
    conn.commit()
    return get_workspace(conn, workspace_id)


def delete_workspace(conn: sqlite3.Connection, workspace_id: str) -> bool:
    cur = conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    conn.commit()
    return cur.rowcount > 0
