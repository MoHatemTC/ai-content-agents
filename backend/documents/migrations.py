"""Schema migrations for the documents & upload domain (M3).

The ``src/`` ingestion lane persists documents/chunks in a single-user SQLite
store (``src.ingestion.store.SQLiteStore``) with no workspace concept and no
notes/status/storage_path columns, so the workspace-scoped read model lives
here, in the FastAPI layer, next to the auth and workspaces tables. The pure
parsing/chunking/quality logic is still reused from ``src/`` — this schema
only owns the per-workspace *records*.

Mirrors Sensei-AI ``docs/DATABASE_SCHEMA.md``:
``documents`` (``id``, ``workspace_id`` FK, ``uploaded_by``, ``title``,
``kind``, ``size_bytes``, ``pages``, ``chunk_count``,
``status('uploaded'|'parsing'|'embedding'|'indexed'|'failed')``,
``storage_path``, ``notes``, ``topics``, ``created_at``) and ``chunks``
(``id``, ``document_id`` FK, ``workspace_id``, ``index``, ``page``,
``content``, ``token_count``).

All statements use ``conn.execute`` so the migration stays inside the
runner's transaction and can be rolled back on failure.
"""

from __future__ import annotations

import sqlite3


def _create_documents_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            uploaded_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            size_bytes INTEGER,
            size_human TEXT NOT NULL DEFAULT '',
            pages INTEGER,
            status TEXT NOT NULL DEFAULT 'uploaded'
                CHECK (status IN ('uploaded', 'parsing', 'embedding', 'indexed', 'failed')),
            tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT,
            storage_path TEXT,
            file_bytes BLOB,
            text TEXT,
            page_offsets_json TEXT NOT NULL DEFAULT '[]',
            text_length INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            page INTEGER,
            token_count INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            section TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents (workspace_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_chunks_workspace ON document_chunks (workspace_id)"
    )


MIGRATIONS: list[tuple[str, object]] = [("documents_tables", _create_documents_tables)]
