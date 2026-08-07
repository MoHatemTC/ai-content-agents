"""Tests for ES256 Supabase access-token verification (the real browser path).

Real Supabase projects sign access tokens with **ES256** using the EC public
key published at ``<url>/auth/v1/.well-known/jwks.json``. These tests mint
real ES256 tokens and verify them against the matching public key, covering the
signature, time, issuer, audience and algorithm checks the frontend depends on.

The JWKS endpoint is injected (offline) by monkeypatching ``_load_jwks`` so the
suite needs no network and no real Supabase project.
"""

from __future__ import annotations

from backend.auth.supabase import (
    SupabaseAuthError,
    SupabaseAuthVerifier,
)
from tests.supabase_test_helpers import (
    TEST_AUDIENCE,
    TEST_EMAIL,
    TEST_ISSUER,
    TEST_PROJECT_URL,
    TEST_USER_ID,
    es256_keypair,
    fake_jwks,
    make_es256_token,
    make_settings,
)

# --------------------------------------------------------------------------- #
# Verifier unit tests (JWKS injected, no network)
# --------------------------------------------------------------------------- #


def _verifier() -> SupabaseAuthVerifier:
    """A verifier configured for ES256 (URL only, no secret/anon required)."""
    return SupabaseAuthVerifier(url=TEST_PROJECT_URL, jwt_secret="", anon_key="")


def _verifier_with_jwks(pub_key, monkeypatch) -> SupabaseAuthVerifier:
    verifier = _verifier()
    jwks = fake_jwks(pub_key)

    def _stub(loader) -> None:
        loader.return_value = jwks

    monkeypatch.setattr(SupabaseAuthVerifier, "_load_jwks", _stub)
    return verifier


def test_es256_verifier_accepts_valid_token(monkeypatch) -> None:
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier,
        "_load_jwks",
        lambda self: fake_jwks(public),
    )
    token = make_es256_token(private)
    profile = verifier.verify(token)
    assert profile.sub == "a1b2c3d4-1111-2222-3333-444455556666"
    assert profile.email == TEST_EMAIL
    assert profile.role == "student"


def test_es256_verifier_accepts_raw_rs_signature(monkeypatch) -> None:
    # Supabase GoTrue emits raw r||s (64-byte) ES256 signatures, not DER. The
    # verifier must accept it even though cryptography's native verify is DER.
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier,
        "_load_jwks",
        lambda self: fake_jwks(public),
    )
    token = make_es256_token(private, raw_signature=True)
    assert len(token.split(".")[2]) == 86  # base64url of 64 raw bytes
    profile = verifier.verify(token)
    assert profile.sub == "a1b2c3d4-1111-2222-3333-444455556666"

    from backend.auth.jwt import signature_size

    assert signature_size(token) == 64


def test_es256_rejects_invalid_signature(monkeypatch) -> None:
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    # Flip a byte inside the signature segment (stays valid base64url, wrong sig).
    parts = make_es256_token(private).split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    token = ".".join(parts)
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "signature" in str(exc)


def test_es256_rejects_other_projects_public_key(monkeypatch) -> None:
    # Token signed by project A but verified against a different project's key.
    signing_private, _ = es256_keypair()
    _, other_public = es256_keypair()
    other_kid = "a1b2c3d4-9999-9999-9999-999999999999"
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier,
        "_load_jwks",
        lambda self: fake_jwks(other_public, kid=other_kid),
    )
    token = make_es256_token(signing_private)
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "signature" in str(exc)


def test_es256_rejects_unknown_kid(monkeypatch) -> None:
    private, _ = es256_keypair()
    _, other_public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(other_public)
    )
    token = make_es256_token(private, kid="a1b2c3d4-1111-1111-1111-111111111111")
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "signature" in str(exc)


def test_es256_self_heals_on_jwks_refresh_after_rotation(monkeypatch) -> None:
    # Stale cache advertises the OLD key; the token was signed with a NEW key
    # that only appears after a refresh. Verification must discard the stale
    # cache, re-fetch and succeed instead of failing "signature verification".
    new_private, new_public = es256_keypair()
    _, old_public = es256_keypair()
    new_kid = "a1b2c3d4-0000-0000-0000-0000000000aa"
    old_kid = "a1b2c3d4-0000-0000-0000-0000000000bb"

    calls = {"n": 0}

    def rotating(self):
        calls["n"] += 1
        if calls["n"] == 1:
            return fake_jwks(old_public, kid=old_kid)
        return fake_jwks(new_public, kid=new_kid)

    verifier = _verifier()
    monkeypatch.setattr(SupabaseAuthVerifier, "_load_jwks", rotating)
    token = make_es256_token(new_private, kid=new_kid)
    profile = verifier.verify(token)
    assert profile.sub == TEST_USER_ID
    assert calls["n"] >= 2


def test_es256_rejects_expired_token(monkeypatch) -> None:
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    token = make_es256_token(private, exp_offset=-3600)
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "expired" in str(exc)


def test_es256_rejects_wrong_issuer(monkeypatch) -> None:
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    token = make_es256_token(private, issuer="https://evil.supabase.co/auth/v1")
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "issuer" in str(exc)


def test_es256_rejects_wrong_audience(monkeypatch) -> None:
    private, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    token = make_es256_token(private, audience="service_role")
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "audience" in str(exc)


def test_es256_rejects_unsupported_algorithm(monkeypatch) -> None:
    _, public = es256_keypair()
    verifier = _verifier()
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    # A token declaring RS256 / none is refused before any key lookup.
    import json

    from tests.supabase_test_helpers import _b64u

    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64u(
        json.dumps({"sub": TEST_USER_ID, "iss": TEST_ISSUER, "aud": TEST_AUDIENCE}).encode()
    )
    token = f"{header}.{payload}.AAAA"
    try:
        verifier.verify(token)
        assert False, "expected SupabaseAuthError"
    except SupabaseAuthError as exc:
        assert "unsupported JWT algorithm" in str(exc)


# --------------------------------------------------------------------------- #
# Endpoint-level tests through FastAPI (ES256 token -> /workspaces)
# --------------------------------------------------------------------------- #


def _es256_app(tmp_path, monkeypatch, public):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    settings = make_settings(
        tmp_path, supabase_url=TEST_PROJECT_URL, supabase_jwt_secret="", supabase_anon_key=""
    )
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    return TestClient(create_app(settings))


def test_protected_endpoint_accepts_valid_es256_token(tmp_path, monkeypatch) -> None:
    private, public = es256_keypair()
    token = make_es256_token(private)
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"workspaces": []}


def test_protected_endpoint_es256_missing_header_returns_401(tmp_path, monkeypatch) -> None:
    _, public = es256_keypair()
    with _es256_app(tmp_path, monkeypatch, public) as client:
        assert client.get("/workspaces").status_code == 401


def test_protected_endpoint_es256_bad_signature_returns_401(tmp_path, monkeypatch) -> None:
    private, public = es256_keypair()
    token = make_es256_token(private) + "x"
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_protected_endpoint_es256_expired_returns_401(tmp_path, monkeypatch) -> None:
    private, public = es256_keypair()
    token = make_es256_token(private, exp_offset=-3600)
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_protected_endpoint_es256_wrong_issuer_returns_401(tmp_path, monkeypatch) -> None:
    private, public = es256_keypair()
    token = make_es256_token(private, issuer="https://evil.supabase.co/auth/v1")
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_protected_endpoint_es256_wrong_audience_returns_401(tmp_path, monkeypatch) -> None:
    private, public = es256_keypair()
    token = make_es256_token(private, audience="service_role")
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_protected_endpoint_es256_creates_user_on_first_access(tmp_path, monkeypatch) -> None:
    import sqlite3

    from tests.supabase_test_helpers import make_settings

    private, public = es256_keypair()
    settings = make_settings(
        tmp_path, supabase_url=TEST_PROJECT_URL, supabase_jwt_secret="", supabase_anon_key=""
    )
    monkeypatch.setattr(
        SupabaseAuthVerifier, "_load_jwks", lambda self: fake_jwks(public)
    )
    with _es256_app(tmp_path, monkeypatch, public) as client:
        response = client.get("/workspaces", headers={"Authorization": f"Bearer {make_es256_token(private)}"})
    assert response.status_code == 200
    conn = sqlite3.connect(settings.platform_db_path)
    try:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (TEST_USER_ID,)).fetchone()
    finally:
        conn.close()
    assert row is not None, "platform user was not created for the ES256 sub"