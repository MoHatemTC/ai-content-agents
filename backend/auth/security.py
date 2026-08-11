"""Password hashing, token generation and display-name helpers (M1).

**TEMPORARY SCAFFOLD.** Supabase is the single auth provider (milestone
decision); this module exists only for the development login scaffold and is
removed when Supabase JWT verification lands.

Standard library only — no new dependency:

* PBKDF2-HMAC-SHA256 for password hashing (``hash_password`` / ``verify_password``),
* ``secrets`` for access/refresh tokens and salts,
* the same two-letter-initial heuristic the frontend uses for avatars.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_HASH_ITERATIONS = 200_000


def generate_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token for access/refresh sessions."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 digest of a session token, the only thing persisted in DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, iterations: int = _HASH_ITERATIONS) -> str:
    """Hash a password as ``"<iterations>$<salt_hex>$<digest_hex>"``."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return f"{iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a ``hash_password`` value."""
    try:
        iterations_s, salt, expected = stored.split("$")
        iterations = int(iterations_s)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return hmac.compare_digest(digest.hex(), expected)


def initials_for(name: str) -> str:
    """Best-effort initials, e.g. ``"Amira Rahman"`` -> ``"AR"`` (max 2)."""
    parts = [part for part in name.strip().split() if part]
    initials = "".join(part[0] for part in parts)[:2].upper()
    return initials or "?"
