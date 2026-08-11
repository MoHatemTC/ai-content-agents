"""Supabase access-token verification for the FastAPI layer.

The Sensei-AI frontend authenticates with **Supabase Auth** and sends
``Authorization: Bearer <supabase_access_token>`` to this backend. The real
Supabase access token is an **ES256** JWT; its header ``kid`` names a public key
that Supabase publishes at ``<url>/auth/v1/.well-known/jwks.json``. The
signature is verified with that public key (asymmetric, no secret needed).

Two fallbacks round out the picture:

* **Local HS256 verification** — used when ``SUPABASE_JWT_SECRET`` is set,
  kept for the offline test suite that mints HS256 tokens (the real browser
  path is ES256 and is unaffected).
* **GoTrue introspection** — POSTs the token to ``GET <url>/auth/v1/user``
  with the anon key when it can run; a useful cross-check but not required
  when the JWKS endpoint is reachable.

Verification is dispatched on the token's actual ``alg`` header, so a real
ES256 token always goes through JWKS regardless of which secret-bearing
environment variables are present.

All paths return the same :class:`SupabaseProfile`, which the dependency layer
maps onto the platform user. Raising only :class:`SupabaseAuthError` keeps
callers a single exception to translate into a 401.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from .jwt import (
    JWKS_ALG_ES256,
    JWKS_ALG_HS256,
    InvalidTokenError,
    peek_alg,
    peek_kid,
    public_key_from_jwk,
    signature_size,
    verify_es256,
    verify_hs256,
)

logger = logging.getLogger(__name__)

_JWKS_CACHE_TTL_SECONDS = 3600


class SupabaseAuthError(Exception):
    """Raised when a token cannot be verified or Supabase is not configured."""


class SupabaseProfile:
    """Verified identity extracted from a Supabase access token.

    ``sub`` is the Supabase user id, which becomes the platform user id. ``role``
    is the *platform* role seed (the JWT's ``role`` is gotrue's ``authenticated``
    and is not meaningful to this API); the authoritative role lives on the
    platform ``user_roles`` table and is resolved by the dependency layer.
    """

    def __init__(
        self,
        *,
        sub: str,
        email: str = "",
        name: str = "",
        role: str = "student",
    ) -> None:
        self.sub = sub
        self.email = email
        self.name = name
        self.role = role

    @classmethod
    def from_mapping(cls, claims: dict[str, Any]) -> SupabaseProfile:
        return cls(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            name=claims.get("name", ""),
            role=claims.get("role", "student"),
        )


class SupabaseAuthVerifier:
    """Verifies Supabase access tokens and returns a :class:`SupabaseProfile`.

    Args:
        url: Supabase project URL (``https://<ref>.supabase.co``). Required for
            ES256 JWKS verification; also used to derive the issuer.
        jwt_secret: The project JWT secret (HS256 local verification / tests).
        anon_key: The publishable anon key, used for GoTrue introspection.
        http_timeout: Seconds to allow a JWKS / GoTrue HTTP request.
    """

    def __init__(
        self,
        *,
        url: str = "",
        jwt_secret: str = "",
        anon_key: str = "",
        http_timeout: float = 10.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.jwt_secret = jwt_secret
        self.anon_key = anon_key
        self.http_timeout = http_timeout
        self._jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def issuer(self) -> str:
        """The Supabase issuer this backend accepts, derived from the URL."""
        return f"{self.url}/auth/v1"

    @property
    def jwks_url(self) -> str:
        """The published JWKS endpoint for this project (ES256 public keys)."""
        return f"{self.url}/auth/v1/.well-known/jwks.json"

    @property
    def configured(self) -> bool:
        """True when at least one verification strategy can run.

        ES256 needs only the project URL (the JWKS endpoint); HS256 needs the
        secret; GoTrue introspection needs URL + anon key.
        """
        return bool(self.jwt_secret) or bool(self.url)

    def verify(self, token: str) -> SupabaseProfile:
        """Verify ``token`` and return the parsed identity.

        The verification strategy is chosen by the token's own ``alg`` header:

        * ``ES256`` → asymmetric verification against the project's published
          JWKS (the real browser path).
        * ``HS256`` → local HMAC verification against ``SUPABASE_JWT_SECRET``
          (offline tests only).

        Raises:
            SupabaseAuthError: With a specific reason when the strategy is
                missing or verification fails.
        """
        if not token:
            raise SupabaseAuthError("missing authorization token")
        if not self.configured:
            raise SupabaseAuthError(
                "Supabase is not configured: set SUPABASE_URL (ES256/JWKS) or "
                "SUPABASE_JWT_SECRET (HS256 local)"
            )
        try:
            alg = peek_alg(token)
        except InvalidTokenError as exc:
            raise SupabaseAuthError(str(exc)) from exc

        if alg == JWKS_ALG_ES256:
            if not self.url:
                raise SupabaseAuthError(
                    "ES256 token but SUPABASE_URL is not set; cannot reach the "
                    "project JWKS endpoint"
                )
            return self._verify_es256_jwks(token)
        if alg == JWKS_ALG_HS256:
            if not self.jwt_secret:
                raise SupabaseAuthError(
                    "HS256 token but SUPABASE_JWT_SECRET is not set"
                )
            return self._verify_local(token)
        raise SupabaseAuthError(f"unsupported JWT algorithm: {alg!r}")

    def _load_jwks(self) -> dict[str, Any]:
        """Fetch (and cache) this project's JWKS from Supabase.

        Cached in-process for ``_JWKS_CACHE_TTL_SECONDS``. Failing to reach the
        endpoint raises :class:`SupabaseAuthError` naming the missing config.
        """
        now = time.time()
        cached_at, cached = self._jwks_cache.get(self.url, (0.0, {}))
        if cached and now - cached_at < _JWKS_CACHE_TTL_SECONDS:
            return cached
        request = urllib.request.Request(
            self.jwks_url, headers={"Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.http_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SupabaseAuthError(
                f"Supabase JWKS endpoint returned HTTP {exc.code} at "
                f"{self.jwks_url}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SupabaseAuthError(
                f"Could not reach Supabase JWKS endpoint {self.jwks_url}: "
                f"{exc.reason}"
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise SupabaseAuthError("Invalid JSON from Supabase JWKS endpoint") from exc
        if not isinstance(body, dict) or not isinstance(body.get("keys"), list):
            raise SupabaseAuthError("Supabase JWKS has no 'keys' array")
        self._jwks_cache[self.url] = (now, body)
        return body

    def _verify_es256_jwks(self, token: str) -> SupabaseProfile:
        """Verify an ES256 token against the project's JWKS.

        Self-healing against key rotation: the token's ``kid`` is matched
        against the cached JWKS; if the signature fails (or the kid is absent /
        unknown), the cache is discarded, the JWKS is re-fetched and every key
        in it is tried before giving up. This turns an intermittent
        "signature verification failed" during Supabase key rotation into a
        verified request.
        """
        kid = peek_kid(token)
        last_error: str | None = None

        for attempt in range(2):
            jwks = self._load_jwks()
            keys = jwks.get("keys", [])
            candidates = [k for k in keys if k.get("kid") == kid] if kid else keys
            if not candidates:
                candidates = keys  # tolerate an absent / rotated kid by trying all
            for jwk in candidates:
                try:
                    public_key = public_key_from_jwk(jwk)
                    claims = verify_es256(
                        token,
                        public_key=public_key,
                        issuer=self.issuer if self.url else None,
                        audience="authenticated",
                    )
                    return SupabaseProfile(
                        sub=claims.get("sub", ""),
                        email=claims.get("email", ""),
                        name=claims.get("name")
                        or (claims.get("user_metadata") or {}).get("name", ""),
                        role=(claims.get("app_metadata") or {}).get("role", "student"),
                    )
                except InvalidTokenError as exc:
                    last_error = str(exc)
            # Key rotation race: the cached JWKS may predate the signing key.
            if attempt == 0:
                self._jwks_cache.pop(self.url, None)
                continue
            break

        jwks = self._load_jwks()
        known_kids = [k.get("kid") for k in jwks.get("keys", [])]
        logger.warning(
            "ES256 token rejected: kid=%r alg=%r sig_bytes=%r known_kids=%r reason=%r",
            kid,
            peek_alg(token),
            signature_size(token),
            known_kids,
            last_error,
        )
        raise SupabaseAuthError(
            last_error
            or f"ES256 token cannot be verified against this project's JWKS "
            f"(kid {kid!r}, known {known_kids!r}); the token may belong to "
            "another Supabase project or predate a key rotation"
        )

    def _verify_local(self, token: str) -> SupabaseProfile:
        try:
            claims = verify_hs256(
                token,
                secret=self.jwt_secret,
                issuer=self.issuer if self.url else None,
                audience="authenticated",
            )
        except InvalidTokenError as exc:
            raise SupabaseAuthError(str(exc)) from exc
        metadata = claims.get("user_metadata") or {}
        name = claims.get("name") or metadata.get("name") or ""
        return SupabaseProfile(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            name=str(name),
            role="student",
        )

    def _verify_gotrue(self, token: str) -> SupabaseProfile:
        request = urllib.request.Request(
            f"{self.issuer}/user",
            headers={"Authorization": f"Bearer {token}", "apikey": self.anon_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.http_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SupabaseAuthError(
                f"Supabase rejected the token (HTTP {exc.code})"
            ) from exc
        except urllib.error.URLError as exc:
            raise SupabaseAuthError(
                f"Could not reach Supabase auth service: {exc.reason}"
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise SupabaseAuthError("Invalid response from Supabase auth service") from exc

        if not isinstance(body, dict) or not body.get("id"):
            raise SupabaseAuthError("Supabase did not return a user identity")
        metadata = body.get("user_metadata") or {}
        return SupabaseProfile(
            sub=str(body["id"]),
            email=str(body.get("email") or ""),
            name=metadata.get("name") or body.get("email") or "",
            role="student",
        )


def default_verifier(*, url: str = "", jwt_secret: str = "", anon_key: str = "", http_timeout: float = 10.0) -> SupabaseAuthVerifier:
    """Convenience factory so app code does not import the class directly."""
    return SupabaseAuthVerifier(
        url=url, jwt_secret=jwt_secret, anon_key=anon_key, http_timeout=http_timeout
    )