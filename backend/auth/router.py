"""Auth API routes (M1) — TEMPORARY SCAFFOLD, replaced during Supabase integration.

**Milestone decision (supersedes the M1 plan):** Supabase is the single auth
provider. These login/logout/me/refresh endpoints, the password hashing in
:mod:`backend.auth.security` and the demo users in :mod:`backend.auth.seed`
are a development scaffold only: they keep the API runnable without a
Supabase project and mirror the frontend's session envelope. During the
Supabase integration milestone this router must be replaced with Supabase JWT
verification (the backend verifies the user's Supabase access token and
derives the user id from it). Do not build new features on top of this
scaffold.

Follows ``docs/FASTAPI_INTEGRATION.md``: login/logout, ``/auth/me`` and
``/auth/refresh``. Unauthenticated ``/auth/me`` returns ``{"user": null}``
(200) so the frontend can detect a signed-out state without an error; invalid
or expired tokens return 401.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.deps import get_db
from backend.errors import ApiError

from . import service
from .schemas import (
    AuthUser,
    GetCurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshSessionRequest,
    RefreshSessionResponse,
    Session,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _session_out(conn: sqlite3.Connection, session: dict) -> Session:
    user = service.user_for_token(conn, session["access_token"])
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return Session(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_at=int(session["expires_at"].timestamp() * 1000),
        user=AuthUser(**user),
    )


@router.post("/login", response_model=LoginResponse, tags=["auth"])
def login(payload: LoginRequest, request: Request, db: Db) -> LoginResponse:
    user = service.authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise ApiError(
            status_code=401,
            code="invalid_credentials",
            message="Email or password is incorrect",
        )
    settings = request.app.state.settings
    session = service.create_session(
        db,
        user["id"],
        access_ttl=settings.access_token_ttl_seconds,
        refresh_ttl=settings.refresh_token_ttl_seconds,
    )
    return LoginResponse(session=_session_out(db, session))


@router.post("/logout", status_code=204, tags=["auth"])
def logout(db: Db, authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        service.revoke_session(db, token)


@router.get("/me", response_model=GetCurrentUserResponse, tags=["auth"])
def me(db: Db, authorization: str = Header(default="")) -> GetCurrentUserResponse:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return GetCurrentUserResponse(user=None)
    user = service.user_for_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return GetCurrentUserResponse(user=AuthUser(**user))


@router.post("/refresh", response_model=RefreshSessionResponse, tags=["auth"])
def refresh(
    payload: RefreshSessionRequest, request: Request, db: Db
) -> RefreshSessionResponse:
    settings = request.app.state.settings
    session = service.refresh_session(
        db,
        payload.refresh_token,
        access_ttl=settings.access_token_ttl_seconds,
        refresh_ttl=settings.refresh_token_ttl_seconds,
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return RefreshSessionResponse(session=_session_out(db, session))
