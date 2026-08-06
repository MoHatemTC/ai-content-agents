"""Seed demo accounts (M1) — TEMPORARY SCAFFOLD.

Supabase is the single auth provider (milestone decision); these demo users
exist only so the development login screen works against the real API without
a Supabase project, and are removed with the scaffold during the Supabase
integration milestone.

Matches the frontend demo users in Sensei-AI ``src/mock/users.ts``. Only runs
when the users table is empty.
"""

from __future__ import annotations

import sqlite3

from .service import create_user

DEMO_USERS: list[dict[str, str]] = [
    {
        "email": "student@demo.com",
        "password": "student",
        "name": "Amira Rahman",
        "role": "student",
    },
    {
        "email": "reviewer@demo.com",
        "password": "reviewer",
        "name": "Noor Patel",
        "role": "reviewer",
    },
    {
        "email": "admin@demo.com",
        "password": "admin",
        "name": "Kenji Ito",
        "role": "admin",
    },
]


def seed_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return
    for user in DEMO_USERS:
        create_user(conn, user["email"], user["password"], user["name"], user["role"])
