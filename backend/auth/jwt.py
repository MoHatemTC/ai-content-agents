"""JWT verification for Supabase access tokens.

Supabase signs user access tokens with one of two algorithms depending on the
project's configuration:

* **ES256** (asymmetric) — the modern default, enforced when the project has
  JWT signing keys enabled. Each token's header carries a ``kid`` matching a
  public key published at ``<project>/auth/v1/.well-known/jwks.json``; the
  signature is verified with that public key (ECDSA / P-256 + SHA-256).
* **HS256** (symmetric) — the legacy path, signed with the project **JWT
  secret** via HMAC-SHA256.

The code below supports both. :func:`peek_alg` inspects the token's unverified
header so the caller can pick the right verifier; :func:`verify_es256` verifies
signature, time, issuer, audience and ``sub`` claims against a public key built
from a JWK; :func:`verify_hs256` does the same against a shared secret (kept
for the local/test path).

Raises :class:`InvalidTokenError` (a ``ValueError``) on any failure, each time
carrying the specific reason so a caller can surface a useful 401 message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

JWKS_ALG_ES256 = "ES256"
JWKS_ALG_HS256 = "HS256"


class InvalidTokenError(ValueError):
    """Raised when a JWT fails verification, with a human-readable reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _b64url_decode(segment: str) -> bytes:
    """Decode a raw (unpadded) base64url segment into bytes."""
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(bytes(padded, "ascii"))


def _load_json(raw: bytes) -> dict[str, Any]:
    """Parse a JSON object from decoded bytes; rejects non-object payloads."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidTokenError("token contains malformed JSON") from exc
    if not isinstance(value, dict):
        raise InvalidTokenError("token payload is not a JSON object")
    return value


def _split(token: str) -> tuple[dict[str, Any], dict[str, Any], str, bytes]:
    """Split a JWT into its header, payload, raw signature and signature bytes."""
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("token does not have the three JWT segments")
    header_encoded, payload_encoded, signature_encoded = parts
    try:
        header = _load_json(_b64url_decode(header_encoded))
        payload = _load_json(_b64url_decode(payload_encoded))
        signature = _b64url_decode(signature_encoded)
    except (ValueError, base64.binascii.Error) as exc:  # binascii.Error subclasses ValueError
        raise InvalidTokenError("token encoding is invalid") from exc
    signing_input = f"{header_encoded}.{payload_encoded}"
    return header, payload, signing_input, signature


def peek_alg(token: str) -> str:
    """Return the ``alg`` from a token's (unverified) header.

    Used to dispatch to the appropriate verifier without first trusting either
    the header or the signature.
    """
    header, _, _, _ = _split(token)
    return str(header.get("alg"))


def peek_kid(token: str) -> str | None:
    """Return the ``kid`` from a token's header, if present."""
    header, _, _, _ = _split(token)
    kid = header.get("kid")
    return str(kid) if kid else None


def public_key_from_jwk(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey:
    """Build an ECDSA public key from an RFC 7517 EC JWK (crv P-256).

    Parses the base64url ``x``/``y`` coordinates into an uncompressed SEC1
    point. Raises ``ValueError``/``InvalidTokenError`` for malformed input.
    """
    curves = {"P-256": ec.SECP256R1(), "P-384": ec.SECP384R1(), "P-521": ec.SECP521R1()}
    curve = curves.get(jwk.get("crv", "P-256"), ec.SECP256R1())
    try:
        x = _b64url_decode(str(jwk["x"]))
        y = _b64url_decode(str(jwk["y"]))
    except KeyError as exc:
        raise InvalidTokenError("JWK is missing EC coordinates") from exc
    except ValueError as exc:
        raise InvalidTokenError("JWK coordinates are not valid base64url") from exc
    point = b"\x04" + x + y  # uncompressed SEC1 point (0x04, x, y)
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(curve, point)
    except ValueError as exc:
        raise InvalidTokenError("JWK does not describe a valid EC public key") from exc


def verify_es256(
    token: str,
    *,
    public_key: ec.EllipticCurvePublicKey,
    issuer: str | None = None,
    audience: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify an ES256-signed JWT against an explicit EC public key.

    Verifies the ECDSA (P-256 / SHA-256) signature, the time claims and the
    issuer/audience/``sub`` claims. Returns the payload on success, else raises
    :class:`InvalidTokenError`.
    """
    header, payload, signing_input, signature = _split(token)
    if header.get("alg") != JWKS_ALG_ES256:
        raise InvalidTokenError(f"unexpected algorithm: {header.get('alg')!r}")
    if "typ" in header and header.get("typ") != "JWT":
        raise InvalidTokenError(f"unexpected token type: {header.get('typ')!r}")

    _verify_es256_signature(public_key, signing_input, signature)

    _verify_time_claims(payload, now if now is not None else time.time())
    _verify_claims(payload, issuer=issuer, audience=audience)
    return payload


def _verify_es256_signature(
    public_key: ec.EllipticCurvePublicKey,
    signing_input: str,
    signature: bytes,
) -> None:
    """Verify an ES256 signature accepting BOTH standard encodings.

    ``cryptography``'s ``ec.ECDSA`` accepts only **DER**-encoded signatures
    (ASN.1 SEQUENCE of two INTEGERs). Many JWT producers — including Go/Node
    (Supabase GoTrue) and PyJWT — emit the **raw** ``r || s`` (fixed-width,
    64 bytes for P-256) form instead. Verify DER first, then transparently
    re-encode a raw signature into DER and retry, so either producer verifies.
    """
    try:
        public_key.verify(
            signature,
            signing_input.encode("utf-8"),
            ec.ECDSA(hashes.SHA256()),
        )
        return
    except InvalidSignature:
        pass

    der = _raw_rs_to_der(signature)
    if der is None:
        raise InvalidTokenError("signature verification failed") from None
    try:
        public_key.verify(
            der,
            signing_input.encode("utf-8"),
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        raise InvalidTokenError("signature verification failed") from None


def _raw_rs_to_der(signature: bytes) -> bytes | None:
    """Convert a raw ``r || s`` P-256 signature (64 bytes) into DER.

    Returns ``None`` when the input is not a 64-byte raw signature (e.g. it is
    already DER, or truncated).
    """
    if len(signature) != 64:
        return None

    def _int_bytes(n: int) -> bytes:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big") or b"\x00"
        return (b"\x00" + b) if b[0] & 0x80 else b

    r_bytes = _int_bytes(int.from_bytes(signature[:32], "big"))
    s_bytes = _int_bytes(int.from_bytes(signature[32:], "big"))
    body = b"\x02" + bytes([len(r_bytes)]) + r_bytes
    body += b"\x02" + bytes([len(s_bytes)]) + s_bytes
    return b"\x30" + bytes([len(body)]) + body


def signature_size(token: str) -> int | None:
    """Decoded byte length of a token's signature segment (diagnostics)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        return len(_b64url_decode(parts[2]))
    except ValueError:
        return None


def _verify_time_claims(payload: dict[str, Any], now: float, leeway: float = 60.0) -> None:
    """Reject a token that is not yet valid or has already expired."""
    exp = payload.get("exp")
    if exp is not None and now >= float(exp) + leeway:
        raise InvalidTokenError("token has expired")
    nbf = payload.get("nbf")
    if nbf is not None and now < float(nbf) - leeway:
        raise InvalidTokenError("token is not valid yet")
    iat = payload.get("iat")
    if iat is not None and now < float(iat) - leeway:
        raise InvalidTokenError("token has been issued in the future")


def _verify_claims(payload: dict[str, Any], *, issuer: str | None, audience: str | None) -> None:
    """Enforce the issuer and audience claims the API expects from Supabase."""
    if issuer is not None and payload.get("iss") != issuer:
        raise InvalidTokenError(
            f"issuer mismatch: expected {issuer!r}, got {payload.get('iss')!r}"
        )
    if audience is not None:
        aud = payload.get("aud")
        if isinstance(aud, str):
            ok = aud == audience
        elif isinstance(aud, list):
            ok = audience in aud
        else:
            ok = False
        if not ok:
            raise InvalidTokenError(f"audience mismatch: expected {audience!r}")
    if not payload.get("sub"):
        raise InvalidTokenError("token has no 'sub' claim")


def verify_hs256(
    token: str,
    *,
    secret: str,
    issuer: str | None = None,
    audience: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify an HS256-signed JWT and return its payload.

    Args:
        token: The raw ``<header>.<payload>.<signature>`` string.
        secret: The shared HMAC secret (the Supabase project JWT secret).
        issuer: Expected ``iss``; ``None`` disables the check.
        audience: Expected ``aud``; ``None`` disables the check.
        now: Optional epoch override (tests) — defaults to the wall clock.

    Raises:
        InvalidTokenError: On any failed check, with a specific reason.
    """
    header, payload, signing_input, signature = _split(token)
    if header.get("alg") != "HS256":
        raise InvalidTokenError(f"unexpected algorithm: {header.get('alg')!r}")
    if "typ" in header and header.get("typ") != "JWT":
        raise InvalidTokenError(f"unexpected token type: {header.get('typ')!r}")

    expected = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, signature):
        raise InvalidTokenError("signature verification failed")

    _verify_time_claims(payload, now if now is not None else time.time())
    _verify_claims(payload, issuer=issuer, audience=audience)
    return payload


def encode_hs256(
    payload: dict[str, Any],
    secret: str,
    *,
    issuer: str | None = None,
    audience: str | None = None,
    expires_in: int = 3600,
) -> str:
    """Build an HS256 JWT for tests and the temporary local demo.

    Production never calls this; it exists so tests can mint realistic
    Supabase-shaped tokens (valid, expired, wrong-issuer, wrong-aud, torn
    signature) and so the backend can be exercised while configuring Supabase.
    """
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    if "iat" not in body:
        body["iat"] = now
    body["exp"] = body["exp"] if "exp" in body else now + expires_in
    if issuer and "iss" not in body:
        body["iss"] = issuer
    if audience and "aud" not in body:
        body["aud"] = audience

    def _seg(obj: object) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    signing = f"{_seg(header)}.{_seg(body)}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return signing + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()