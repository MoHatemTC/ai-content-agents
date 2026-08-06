"""Service functions for the auth domain (M1) — TEMPORARY SCAFFOLD.

Supabase is the single auth provider (milestone decision); this password,
session and demo-user implementation exists so the API runs without a
Supabase project and must be replaced by Supabase JWT verification during the
Supabase integration milestone. Do not build M3+ features on top of it.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .security import (
    generate_token,
    hash_password,
    hash_token,
    initials_for,
    verify_password,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def create_user(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    name: str,
    role: str,
) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, email.strip().lower(), hash_password(password), now().isoformat()),
    )
    conn.execute(
        "INSERT INTO profiles (id, full_name, initials, created_at) VALUES (?, ?, ?, ?)",
        (user_id, name, initials_for(name), now().isoformat()),
    )
    conn.execute(
        "INSERT INTO user_roles (id, user_id, role) VALUES (?, ?, ?)",
        (str(uuid.uuid4()), user_id, role),
    )
    conn.commit()
    return user_id


def find_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute(
        """
        SELECT u.id, u.email, u.password_hash, p.full_name, p.initials, r.role
        FROM users u
        LEFT JOIN profiles p ON p.id = u.id
        LEFT JOIN user_roles r ON r.user_id = u.id
        WHERE u.email = ?
        """,
        (email.strip().lower(),),
    ).fetchone()
    if row is None:
        return None
    user = dict(row)
    user["role"] = user["role"] or "student"
    return user


def authenticate_user(
    conn: sqlite3.Connection, email: str, password: str
) -> dict | None:
    user = find_user_by_email(conn, email)
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return user


def create_session(
    conn: sqlite3.Connection, user_id: str, access_ttl: int, refresh_ttl: int
) -> dict:
    access_token = generate_token()
    refresh_token = generate_token()
    session_id = str(uuid.uuid4())
    now_dt = now()
    expires_at = now_dt + timedelta(seconds=access_ttl)
    refresh_expires_at = now_dt + timedelta(seconds=refresh_ttl)
    conn.execute(
        """
        INSERT INTO sessions
            (id, user_id, access_token_hash, refresh_token_hash, expires_at, refresh_expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            user_id,
            hash_token(access_token),
            hash_token(refresh_token),
            expires_at.isoformat(),
            refresh_expires_at.isoformat(),
            now_dt.isoformat(),
        ),
    )
    conn.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "refresh_expires_at": refresh_expires_at,
    }


def revoke_session(conn: sqlite3.Connection, access_token: str) -> None:
    conn.execute(
        "UPDATE sessions SET revoked = 1 WHERE access_token_hash = ?",
        (hash_token(access_token),),
    )
    conn.commit()


def refresh_session(
    conn: sqlite3.Connection,
    refresh_token: str,
    access_ttl: int,
    refresh_ttl: int,
) -> dict | None:
    row = conn.execute(
        """
        SELECT id, user_id, revoked, refresh_expires_at
        FROM sessions
        WHERE refresh_token_hash = ?
        """,
        (hash_token(refresh_token),),
    ).fetchone()
    if row is None or row["revoked"]:
        return None
    expires_at = datetime.fromisoformat(row["refresh_expires_at"])
    if expires_at < now():
        return None
    conn.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    return create_session(conn, row["user_id"], access_ttl, refresh_ttl)


def user_for_token(conn: sqlite3.Connection, access_token: str) -> dict | None:
    row = conn.execute(
        """
        SELECT s.id, s.expires_at, s.revoked, u.id AS user_id, u.email,
               p.full_name, p.initials, r.role
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN profiles p ON p.id = u.id
        LEFT JOIN user_roles r ON r.user_id = u.id
        WHERE s.access_token_hash = ?
        """,
        (hash_token(access_token),),
    ).fetchone()
    if row is None or row["revoked"]:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at < now():
        return None
    return {
        "id": row["user_id"],
        "email": row["email"],
        "name": row["full_name"],
        "initials": row["initials"],
        "role": row["role"] or "student",
    }
