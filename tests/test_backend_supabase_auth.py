"""Tests for the Supabase JWT authentication layer (Phase-8 integration).

Protected endpoints require a verified Supabase access token. These tests mint
real HS256 tokens (valid / expired / wrong-issuer / wrong-aud / torn-signature)
and assert the 401/200 behaviour the frontend depends on.
"""

from __future__ import annotations

from backend.auth.supabase import SupabaseAuthError, SupabaseAuthVerifier
from tests.supabase_test_helpers import (
    TEST_EMAIL,
    TEST_JWT_SECRET,
    TEST_PROJECT_URL,
    TEST_USER_ID,
    auth_headers,
    make_token,
)

# --------------------------------------------------------------------------- #
# Verifier unit tests (fast, no HTTP)
# --------------------------------------------------------------------------- #


def verifier() -> SupabaseAuthVerifier:
    return SupabaseAuthVerifier(
        url=TEST_PROJECT_URL, jwt_secret=TEST_JWT_SECRET, anon_key="anon"
    )


def test_verifier_accepts_valid_token() -> None:
    token = make_token()
    profile = verifier().verify(token)
    assert profile.sub == TEST_USER_ID
    assert profile.email == TEST_EMAIL
    assert profile.role == "student"


def test_verifier_rejects_bad_signature() -> None:
    token = make_token() + "extra"
    try:
        verifier().verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "signature" in str(exc)


def test_verifier_rejects_expired_token() -> None:
    token = make_token(exp_offset=-3600)
    try:
        verifier().verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "expired" in str(exc)


def test_verifier_rejects_wrong_issuer() -> None:
    token = make_token(issuer="https://evil.supabase.co/auth/v1")
    try:
        verifier().verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "issuer" in str(exc)


def test_verifier_rejects_wrong_audience() -> None:
    token = make_token(audience="service_role")
    try:
        verifier().verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "audience" in str(exc)


def test_verifier_rejects_missing_token() -> None:
    try:
        verifier().verify("")
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "missing" in str(exc)


def test_verifier_reports_unconfigured() -> None:
    v = SupabaseAuthVerifier(url="", jwt_secret="", anon_key="")
    try:
        v.verify(make_token())
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "not configured" in str(exc)


# --------------------------------------------------------------------------- #
# Endpoint-level tests through FastAPI
# --------------------------------------------------------------------------- #


def test_protected_endpoint_accepts_valid_supabase_token(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {"workspaces": []}


def test_protected_endpoint_missing_header_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    with make_app(tmp_path) as client:
        response = client.get("/workspaces")

    assert response.status_code == 401


def test_protected_endpoint_invalid_token_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    with make_app(tmp_path) as client:
        response = client.get(
            "/workspaces", headers={"Authorization": "Bearer garbage"}
        )

    assert response.status_code == 401


def test_protected_endpoint_expired_token_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    token = make_token(exp_offset=-3600)
    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_protected_endpoint_wrong_issuer_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    token = make_token(issuer="https://evil.supabase.co/auth/v1")
    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_protected_endpoint_wrong_audience_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    token = make_token(audience="service_role")
    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_protected_endpoint_wrong_signature_returns_401(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    token = make_token(secret="some-other-secret")
    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_protected_endpoint_creates_user_on_first_access(tmp_path) -> None:
    import sqlite3

    from tests.supabase_test_helpers import TEST_USER_ID, make_app, make_settings

    settings = make_settings(tmp_path)
    with make_app(tmp_path) as client:
        response = client.get("/workspaces", headers=auth_headers())

    assert response.status_code == 200
    conn = sqlite3.connect(settings.platform_db_path)
    try:
        row = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (TEST_USER_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "platform user was not created for the Supabase sub"
    assert row[0] == TEST_USER_ID


def test_valid_user_can_access_owned_resource_after_supabase_login(tmp_path) -> None:
    from tests.supabase_test_helpers import make_app

    with make_app(tmp_path) as client:
        headers = auth_headers()
        created = client.post(
            "/workspaces",
            json={"name": "My Workspace", "description": "phase 8"},
            headers=headers,
        )
        assert created.status_code == 201
        workspace_id = created.json()["workspace"]["id"]

        listed = client.get("/workspaces", headers=headers)
        assert listed.status_code == 200
        assert workspace_id in [w["id"] for w in listed.json()["workspaces"]]