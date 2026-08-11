"""Shared SQLite connection helper for the backend package.

Keeps the ``PRAGMA foreign_keys = ON`` setup in one place so the migration
runner and every service open connections identically.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enforced and Row access.

    ``check_same_thread=False`` allows FastAPI's yield-based ``get_db``
    dependency to close the connection from a different worker thread than the
    one that created it (Starlette can resume the generator on another
    threadpool thread). Each call returns a fresh, private connection, so the
    relaxed check never means shared use across threads.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
