"""Environment-backed settings for the FastAPI layer.

The domain code in ``src/`` reads the same environment variables directly (e.g.
``PLATFORM_DB_PATH`` in :mod:`src.validation.store`), so this module reuses
those names instead of inventing parallel ones — one source of truth per knob.
Settings are a frozen dataclass so the app factory can receive an explicit
instance in tests without touching the process environment.

No domain module is imported here except a pure helper
(:func:`src.llm_gateway.default_model`) so this stays import-safe even when the
LLM gateway is not configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from src.llm_gateway import default_model

APP_NAME = "Content Agents API"


def _cors_origins(raw: str | None) -> list[str]:
    """Split a comma-separated ``CORS_ORIGINS`` value into origins.

    Defaults to a permissive development default; production must set
    ``CORS_ORIGINS`` to explicit origins. ``*`` and ``allow_credentials`` are
    mutually exclusive in most browsers, so credentials stay off by default.
    """
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    """Read the backend's configuration from the environment once, at load."""

    app_name: str = APP_NAME
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    platform_db_path: str = field(
        default_factory=lambda: os.getenv("PLATFORM_DB_PATH") or "ingestion.db"
    )
    chroma_dir: str = field(
        default_factory=lambda: os.getenv("CHROMA_DIR") or ".chroma"
    )
    default_model: str = field(default_factory=default_model)
    cors_origins: list[str] = field(
        default_factory=lambda: _cors_origins(os.getenv("CORS_ORIGINS"))
    )
    access_token_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("AUTH_ACCESS_TTL_SECONDS", "3600"))
    )
    refresh_token_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("AUTH_REFRESH_TTL_SECONDS", "86400"))
    )
    # Matches the Supabase free-tier per-file default the future frontend
    # storage is aligned to; the BACKEND_CONTRACT.md upload row requires a 413
    # when a file exceeds it.
    max_upload_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
        )
    )
    # ------------------------------------------------------------------ #
    # Supabase (single auth provider)
    #
    # The frontend authenticates with Supabase Auth and sends the resulting
    # access token to this API. Verification is local HS256 when
    # SUPABASE_JWT_SECRET is set, otherwise GoTrue introspection against
    # SUPABASE_URL (issuer is derived as <SUPABASE_URL>/auth/v1).
    # ------------------------------------------------------------------ #
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_jwt_secret: str = field(
        default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET", "")
    )
    supabase_anon_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", "")
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, cached for the app's lifetime."""
    return Settings()
