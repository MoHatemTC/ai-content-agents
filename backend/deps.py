"""FastAPI dependency-injection helpers.

M0 shipped the settings dependencies; M1 adds the SQLite connection
(:func:`get_db`), the authenticated user (:func:`get_current_user`) and the
role gate (:func:`require_role`). All routers share these rather than opening
connections themselves.

**Note (M3):** :func:`get_current_user` / :func:`require_role` resolve the
caller through the M1 password-auth scaffold, which is temporary. Supabase is
the single auth provider; during the Supabase integration milestone these
dependencies are rewritten to verify a Supabase access token and derive the
user id from it. Do not build M3+ authorisation decisions on the scaffold's
role model.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from backend.auth import service as auth_service
from backend.auth.schemas import AuthUser
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
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: str = Header(default=""),
) -> AuthUser:
    """Resolve the ``Authorization: Bearer <token>`` caller.

    Raises:
        HTTPException: 401 when the header is missing or the token is unknown,
            revoked or expired.
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    user = auth_service.user_for_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
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
