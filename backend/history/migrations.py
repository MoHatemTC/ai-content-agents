"""Database migrations for the history package."""

from __future__ import annotations

import sqlite3


def create_history_table(conn: sqlite3.Connection) -> None:
    """Create the history table for generation-run persistence.

    Mirrors the UI's ``WsHistoryRow`` shape plus the workspace/user scoping
    used by the other platform tables (and the Supabase ``public.history``
    schema aligned in ``supabase/migrations/``).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            doc TEXT NOT NULL,
            status TEXT NOT NULL,
            quality REAL NOT NULL,
            review TEXT NOT NULL,
            items INTEGER NOT NULL,
            chat_id TEXT,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_workspace ON history (workspace_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON history (user_id)")


MIGRATIONS: list[tuple[str, type(create_history_table)]] = [
    ("m7_001_history", create_history_table),
]
