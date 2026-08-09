"""FastAPI dependency-injection helpers.

M0 shipped the settings dependencies; M1+ adds the SQLite connection
(:func:`get_db`), the authenticated user (:func:`get_current_user`) and the
role gate (:func:`require_role`). All routers share these rather than opening
connections themselves.

Auth crossing is **Supabase-first**: :func:`get_current_user` verifies a
Supabase access token (see :mod:`backend.auth.supabase`) and maps the verified
``sub`` to the platform user. The M1 password-scaffold login endpoints remain
for a scaffolded login screen, but protected endpoints no longer accept the
scaffold's opaque tokens — they require a Supabase JWT.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from backend.auth import service as auth_service
from backend.auth.schemas import AuthUser
from backend.auth.supabase import SupabaseAuthError, SupabaseAuthVerifier
from backend.config import Settings
from backend.config import get_settings as _get_env_settings
from backend.db import connect


def get_settings(request: Request) -> Settings:
    """FastAPI dependency returning app settings from app.state if available, else environment settings."""
    if hasattr(request.app.state, "settings"):
        return request.app.state.settings
    return _get_env_settings()


settings_dependency = get_settings


def app_settings(request: Request) -> Settings:
    """Return the settings instance bound to this app (from ``app.state``)."""
    return get_settings(request)


def get_db(request: Request):
    """Yield a per-request SQLite connection and always close it."""
    conn = connect(request.app.state.settings.platform_db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    request: Request,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: str = Header(default=""),
) -> AuthUser:
    """Resolve the ``Authorization: Bearer <token>`` caller.

    The token is a **Supabase access token** obtained by the frontend from
    Supabase Auth. It is verified per :class:`backend.auth.supabase
    .SupabaseAuthVerifier` (local HS256 when ``SUPABASE_JWT_SECRET`` is set,
    otherwise GoTrue introspection against ``SUPABASE_URL``), then the verified
    ``sub`` is mapped to the platform user, creating it on first login.

    Raises:
        HTTPException: 401 when the header is missing or the token is invalid,
            expired or fails signature/issuer/audience checks.
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    settings = get_settings(request)
    verifier = SupabaseAuthVerifier(
        url=settings.supabase_url,
        jwt_secret=settings.supabase_jwt_secret,
        anon_key=settings.supabase_anon_key,
    )
    try:
        profile = verifier.verify(token)
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc
    user = auth_service.ensure_supabase_user(
        db,
        sub=profile.sub,
        email=profile.email,
        name=profile.name,
        role=profile.role,
    )
    # Keep the platform role in sync with Supabase's user_roles table (the
    # same source the frontend reads), so staff-gated endpoints match the UI.
    auth_service.sync_role_from_supabase(
        db,
        user_id=user["id"],
        access_token=token,
        supabase_url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
    )
    user = auth_service.find_user_by_id(db, user["id"]) or user
    return AuthUser(**user)


def require_role(*roles: str) -> Callable[..., AuthUser]:
    """Return a dependency requiring the caller to hold one of ``roles``."""

    def _require(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _require


def require_workspace_member(db_path: str, workspace_id: str, user: AuthUser) -> None:
    """Ensure workspace exists and caller is owner/member."""
    from backend.errors import ApiError

    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT owner_id FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        if row is None:
            raise ApiError(
                status_code=404, code="not_found", message="Workspace not found"
            )
        if row[0] != user.id:
            raise ApiError(
                status_code=403,
                code="forbidden",
                message="Not allowed to access this workspace",
            )
    finally:
        conn.close()
