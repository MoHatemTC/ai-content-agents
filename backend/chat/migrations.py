"""Database migrations for the chat package (M6)."""

from __future__ import annotations

import sqlite3


def create_chats_table(conn: sqlite3.Connection) -> None:
    """Create chats and chat_messages tables for chat persistence."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            citations_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats (workspace_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat ON chat_messages (chat_id)"
    )


MIGRATIONS: list[tuple[str, type(create_chats_table)]] = [
    ("m6_001_chats", create_chats_table),
]
