"""Tests for the Phase 8 M0 backend scaffold.

Covers the app factory, the contract error envelope, CORS middleware and the
migration runner. Business routers do not exist yet, so the exception-handler
tests mount the handlers on throwaway apps rather than fabricating endpoints.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ApiError, register_exception_handlers
from backend.main import create_app
from backend.migrations import apply_pending


def _settings(tmp_path) -> Settings:
    return Settings(platform_db_path=str(tmp_path / "platform.db"))


# --------------------------------------------------------------------------- #
# App factory / health
# --------------------------------------------------------------------------- #


def test_health_endpoint_reports_ok(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Content Agents API"


def test_create_app_binds_settings_to_state(tmp_path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    assert app.state.settings is settings


def test_app_startup_runs_pending_migrations(tmp_path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)):
        pass

    conn = sqlite3.connect(settings.platform_db_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("schema_migrations",),
        ).fetchone()
    finally:
        conn.close()
    assert table is not None


# --------------------------------------------------------------------------- #
# Error envelope
# --------------------------------------------------------------------------- #


def test_unknown_route_returns_error_envelope(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": {}}
    }


def test_api_error_returns_envelope_with_code(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    @app.get("/boom")
    def boom() -> None:
        raise ApiError(status_code=429, message="Model rate limited")

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["message"] == "Model rate limited"


def test_api_error_accepts_explicit_code(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    @app.get("/bad-login")
    def bad_login() -> None:
        raise ApiError(
            status_code=401,
            code="invalid_credentials",
            message="Email or password is wrong",
        )

    with TestClient(app) as client:
        response = client.get("/bad-login")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_validation_error_returns_422_envelope(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    @app.get("/needs-int/{value}")
    def needs_int(value: int) -> int:
        return value

    with TestClient(app) as client:
        response = client.get("/needs-int/not-an-int")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert "errors" in body["details"]


def test_unhandled_error_returns_500_envelope(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    @app.get("/crashes")
    def crashes() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/crashes")

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "internal_error"
    assert "RuntimeError" in body["message"]


def test_register_exception_handlers_is_idempotent(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    register_exception_handlers(app)  # must not raise

    with TestClient(app) as client:
        response = client.get("/no-such-route")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #


def test_cors_headers_present_by_default(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_origins_come_from_settings(tmp_path) -> None:
    settings = Settings(
        platform_db_path=str(tmp_path / "platform.db"),
        cors_origins=["http://localhost:3001"],
    )
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:3001"})
        denied = client.get("/health", headers={"Origin": "http://evil.example"})

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert denied.headers.get("access-control-allow-origin") is None


# --------------------------------------------------------------------------- #
# Migration runner
# --------------------------------------------------------------------------- #


def _create_thing(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE things (id INTEGER PRIMARY KEY)")


def test_apply_pending_applies_and_records_in_order(tmp_path) -> None:
    db = str(tmp_path / "m.db")
    migrations = [("a_create_things", _create_thing)]

    applied = apply_pending(db, migrations)

    assert applied == ["a_create_things"]
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("things",),
        ).fetchone()
    finally:
        conn.close()
    assert [row[0] for row in rows] == ["a_create_things"]
    assert table is not None


def test_apply_pending_is_idempotent(tmp_path) -> None:
    db = str(tmp_path / "m.db")
    migrations = [("a_create_things", _create_thing)]

    first = apply_pending(db, migrations)
    second = apply_pending(db, migrations)

    assert first == ["a_create_things"]
    assert second == []


def test_apply_pending_skips_already_applied_by_name(tmp_path) -> None:
    db = str(tmp_path / "m.db")
    later = [
        ("a_create_things", _create_thing),
        (
            "b_create_other",
            lambda conn: conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)"),
        ),
    ]

    apply_pending(db, [later[0]])
    applied = apply_pending(db, later)

    assert applied == ["b_create_other"]


def test_failed_migration_rolls_back(tmp_path) -> None:
    db = str(tmp_path / "m.db")

    def bad(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE doomed (id INTEGER PRIMARY KEY)")
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        apply_pending(db, [("bad_migration", bad)])

    conn = sqlite3.connect(db)
    try:
        versions = conn.execute("SELECT version FROM schema_migrations").fetchall()
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("doomed",),
        ).fetchone()
    finally:
        conn.close()
    assert versions == []
    assert table is None


def test_empty_migrations_creates_tracking_table(tmp_path) -> None:
    db = str(tmp_path / "m.db")
    assert apply_pending(db, []) == []

    conn = sqlite3.connect(db)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("schema_migrations",),
        ).fetchone()
    finally:
        conn.close()
    assert table is not None
