"""Shared helpers for testing the Supabase JWT auth path.

Protected endpoints now require a **Supabase access token**, so the backend
test suite no longer authenticates through the M1 ``/auth/login`` scaffold.
These helpers mint realistic Supabase-shaped HS256 tokens (valid, expired,
wrong-issuer, wrong-aud, torn signature) signed with a fixed test secret and
build a ``Settings``/app pair that verifies them locally — no network, no real
Supabase project.

Mirrors ``tests/conftest.py``'s philosophy: the suite must depend on the
repository and nothing else.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from fastapi.testclient import TestClient

from backend.auth.jwt import encode_hs256
from backend.config import Settings
from backend.main import create_app

# A fixed, throwaway secret — never a real Supabase project secret.
TEST_JWT_SECRET = "phase8-test-secret-0123456789"
TEST_PROJECT_URL = "https://test-project.supabase.co"
TEST_ISSUER = f"{TEST_PROJECT_URL}/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_USER_ID = "a1b2c3d4-1111-2222-3333-444455556666"
TEST_EMAIL = "student@example.com"
TEST_NAME = "Test Student"


def make_settings(tmp_path, **overrides: Any) -> Settings:
    """Build app settings that verify Supabase tokens locally, offline."""
    base: dict[str, Any] = {
        "platform_db_path": str(tmp_path / "platform.db"),
        "supabase_url": TEST_PROJECT_URL,
        "supabase_jwt_secret": TEST_JWT_SECRET,
        "supabase_anon_key": "test-anon-key",
    }
    base.update(overrides)
    return Settings(**base)


def make_app(tmp_path, **overrides: Any) -> TestClient:
    """Return a TestClient whose protected endpoints verify Supabase tokens."""
    return TestClient(create_app(make_settings(tmp_path, **overrides)))


def make_token(
    *,
    sub: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    name: str = TEST_NAME,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    exp_offset: int = 3600,
    secret: str = TEST_JWT_SECRET,
    extra: dict[str, Any] | None = None,
) -> str:
    """Mint an HS256 token shaped like a Supabase access token."""
    payload: dict[str, Any] = {"sub": sub, "email": email, "name": name}
    if extra:
        payload.update(extra)
    return encode_hs256(
        payload,
        secret,
        issuer=issuer,
        audience=audience,
        expires_in=exp_offset,
    )


def expired_token() -> str:
    return make_token(exp_offset=-3600)


def auth_headers(token: str | None = None, **token_kwargs: Any) -> dict[str, str]:
    """Return an Authorization header carrying a (default) valid token."""
    return {"Authorization": f"Bearer {token or make_token(**token_kwargs)}"}


# --------------------------------------------------------------------------- #
# ES256 (asymmetric, JWKS) helpers — mirror a real Supabase access token
# --------------------------------------------------------------------------- #

# A throwaway "project" public key id; not derived from a real Supabase project.
TEST_ES256_KID = "cafe0000-1111-2222-3333-444455556666"


def _b64u(raw: bytes) -> str:
    """Base64url-encode raw bytes without padding (JWT/JWK style)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def es256_keypair():
    """Generate a fresh P-256 keypair for signing / verifying test tokens."""
    from cryptography.hazmat.primitives.asymmetric import ec

    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key()


def jwk_from_public_key(
    public_key, kid: str = TEST_ES256_KID
) -> dict[str, Any]:
    """Serialize an EC public key into an RFC 7517 JWK (crv ``P-256``)."""
    from cryptography.hazmat.primitives.asymmetric import ec

    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    nums = public_key.public_numbers()
    size = (public_key.key_size + 7) // 8
    return {
        "kty": "EC",
        "crv": "P-256",
        "kid": kid,
        "use": "sig",
        "alg": "ES256",
        "x": _b64u(nums.x.to_bytes(size, "big")),
        "y": _b64u(nums.y.to_bytes(size, "big")),
    }


def fake_jwks(pub_key, kid: str = TEST_ES256_KID) -> dict[str, Any]:
    """Wrap a public key in the Supabase JWKS response shape."""
    return {"keys": [jwk_from_public_key(pub_key, kid)]}


def encode_es256(
    payload: dict[str, Any],
    private_key,
    *,
    issuer: str,
    audience: str,
    expires_in: int,
    kid: str = TEST_ES256_KID,
    raw_signature: bool = False,
) -> str:
    """Mint an ES256 JWT shaped like a real Supabase access token.

    ``raw_signature=True`` encodes the signature as fixed-width ``r || s``
    (64 bytes) — the form used by Go/Node (Supabase GoTrue) and PyJWT —
    instead of ``cryptography``'s default DER, to exercise both verifier paths.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    now = int(time.time())
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    body = dict(payload)
    if "iat" not in body:
        body["iat"] = now
    body["exp"] = body.get("exp", now + expires_in)
    if issuer and "iss" not in body:
        body["iss"] = issuer
    if audience and "aud" not in body:
        body["aud"] = audience

    def _seg(obj: object) -> str:
        return _b64u(json.dumps(obj, separators=(",", ":")).encode())

    signing = f"{_seg(header)}.{_seg(body)}"
    signature = private_key.sign(signing.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    if raw_signature:
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        r, s = decode_dss_signature(signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing + "." + _b64u(signature)


def make_es256_token(
    private_key,
    *,
    sub: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    name: str = TEST_NAME,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    exp_offset: int = 3600,
    kid: str = TEST_ES256_KID,
    raw_signature: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    """Mint an ES256 token shaped like a real Supabase access token."""
    payload: dict[str, Any] = {"sub": sub, "email": email, "name": name}
    if extra:
        payload.update(extra)
    return encode_es256(
        payload,
        private_key,
        issuer=issuer,
        audience=audience,
        expires_in=exp_offset,
        kid=kid,
        raw_signature=raw_signature,
    )
