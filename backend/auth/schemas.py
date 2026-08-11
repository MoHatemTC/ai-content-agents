"""Request/response schemas for the auth endpoints.

Shapes match Sensei-AI ``src/types/api/auth.contracts.ts`` exactly: login,
logout, ``/me`` and refresh all use the ``session``/``user`` envelopes from
``docs/FASTAPI_INTEGRATION.md``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

UserRole = Literal["student", "reviewer", "admin"]


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUser(BaseModel):
    id: str
    email: str
    name: str
    initials: str
    role: UserRole


class Session(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    user: AuthUser


class LoginResponse(BaseModel):
    session: Session


class RefreshSessionRequest(BaseModel):
    refresh_token: str


class RefreshSessionResponse(BaseModel):
    session: Session


class GetCurrentUserResponse(BaseModel):
    user: AuthUser | None
