"""Schema migrations for the workspaces domain (M2).

Workspaces are a FastAPI-layer concern (the ``src/`` domain is single-user).
``assets``/``pending_review`` remain 0 until later milestones add the
per-workspace assets and review tables; ``document_count`` became real at M3,
read live from the ``documents`` table (see
:func:`backend.workspaces.service.get_workspace_docs`).
"""

from __future__ import annotations

import sqlite3


def _create_workspaces_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            description TEXT,
            accent TEXT NOT NULL DEFAULT 'primary',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces (owner_id)"
    )


MIGRATIONS: list[tuple[str, object]] = [
    ("workspaces_tables", _create_workspaces_tables)
]
