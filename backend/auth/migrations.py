"""Schema migrations for the authentication domain (M1).

**TEMPORARY SCAFFOLD.** Supabase is the single auth provider (milestone
decision); these account tables belong to the development-only password-auth
scaffold and must be removed when the Supabase integration milestone lands.
They exist because the domain layer in ``src/`` is single-user and has none.
All statements use ``conn.execute`` (rather than ``executescript``) so each
migration stays inside the runner's transaction and can be rolled back on
failure.
"""

from __future__ import annotations

import sqlite3


def _create_auth_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL,
            initials TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_roles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('student', 'reviewer', 'admin')),
            UNIQUE (user_id, role)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            access_token_hash TEXT NOT NULL UNIQUE,
            refresh_token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            refresh_expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles (user_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_refresh ON sessions (refresh_token_hash)"
    )


MIGRATIONS: list[tuple[str, object]] = [("auth_tables", _create_auth_tables)]
