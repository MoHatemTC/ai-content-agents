"""Lightweight SQLite migration runner for the backend.

The domain stores in ``src/`` initialise their own tables with
``CREATE TABLE IF NOT EXISTS`` and have no versioning; Phase 8 adds new tables
and columns (workspaces, auth, chat history, …) on top of those files, so a
small ordered-migration mechanism is needed.

Design:

* A migration is a ``(name, callable)`` pair; the name is its stable version,
  never its position in the list (inserting one mid-list must not re-run
  already-applied ones).
* Applied names are recorded in a ``schema_migrations`` table next to the
  domain tables.
* Each migration runs inside a transaction; a failure rolls it back, leaving
  the database untouched.
* ``MIGRATIONS`` is the ordered registry that later milestones append to. M0
  shipped it empty; M1/M2 register the auth and workspace tables from the
  domain packages (:mod:`backend.auth.migrations`,
  :mod:`backend.workspaces.migrations`).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from backend.auth.migrations import MIGRATIONS as AUTH_MIGRATIONS
from backend.chat.migrations import MIGRATIONS as CHATS_MIGRATIONS
from backend.documents.migrations import MIGRATIONS as DOCUMENTS_MIGRATIONS
from backend.history.migrations import MIGRATIONS as HISTORY_MIGRATIONS
from backend.workspaces.migrations import MIGRATIONS as WORKSPACES_MIGRATIONS

Migration = Callable[[sqlite3.Connection], None]

MIGRATIONS: list[tuple[str, Migration]] = [
    *AUTH_MIGRATIONS,
    *WORKSPACES_MIGRATIONS,
    *DOCUMENTS_MIGRATIONS,
    *CHATS_MIGRATIONS,
    *HISTORY_MIGRATIONS,
]


def default_db_path() -> str:
    """Resolve the platform database path the same way ``PlatformStore`` does."""
    return os.getenv("PLATFORM_DB_PATH") or "ingestion.db"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_tracking(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def applied_versions(db_path: str) -> set[str]:
    """Return the set of migration names already recorded for ``db_path``."""
    conn = _connect(db_path)
    try:
        _ensure_tracking(conn)
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def apply_pending(
    db_path: str,
    migrations: Sequence[tuple[str, Migration]],
) -> list[str]:
    """Apply every not-yet-applied migration, in order.

    Args:
        db_path: SQLite file to migrate (created if missing).
        migrations: Ordered ``(name, callable)`` migration list.

    Returns:
        The names of the migrations applied by this call (empty when none were
        pending).

    Raises:
        RuntimeError: If a migration fails; that migration is rolled back and
            nothing after it is attempted.
    """
    applied = applied_versions(db_path)
    result: list[str] = []
    conn = _connect(db_path)
    try:
        _ensure_tracking(conn)
        for name, migration in migrations:
            if name in applied:
                continue
            conn.execute("BEGIN")
            try:
                migration(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (name, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                result.append(name)
            except BaseException as exc:
                conn.rollback()
                raise RuntimeError(
                    f"Migration {name!r} failed and was rolled back: {exc}"
                ) from exc
    finally:
        conn.close()
    return result


def run_pending(db_path: str | None = None) -> list[str]:
    """Apply all registered :data:`MIGRATIONS` to the platform database.

    Args:
        db_path: Override the platform database path (defaults to
            ``PLATFORM_DB_PATH``/``ingestion.db``).
    """
    return apply_pending(db_path or default_db_path(), MIGRATIONS)
