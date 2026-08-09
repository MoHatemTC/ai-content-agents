"""Workspaces API routes (M2)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.schemas import AuthUser
from backend.deps import get_current_user, get_db
from backend.errors import ApiError
from backend.workspaces.schemas import (
    CreateWorkspaceRequest,
    CreateWorkspaceResponse,
    GetWorkspaceResponse,
    GetWorkspacesResponse,
    PatchWorkspace,
    WorkspaceData,
)

from . import service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]
User = Annotated[AuthUser, Depends(get_current_user)]


def _empty_workspace_data() -> WorkspaceData:
    return WorkspaceData(
        docs=[],
        questions=[],
        flashcards=[],
        chats=[],
        history=[],
        weakTopics=[],
        audit=[],
    )


def _require_owner(row: sqlite3.Row, user: AuthUser) -> None:
    if row["owner_id"] != user.id:
        raise ApiError(
            status_code=403,
            code="forbidden",
            message="Not allowed to access this workspace",
        )


@router.get("", response_model=GetWorkspacesResponse)
def list_workspaces(db: Db, user: User) -> GetWorkspacesResponse:
    return GetWorkspacesResponse(workspaces=service.list_workspaces(db, user.id))


@router.post("", response_model=CreateWorkspaceResponse, status_code=201)
def create_workspace(
    payload: CreateWorkspaceRequest, db: Db, user: User
) -> CreateWorkspaceResponse:
    workspace, created = service.create_workspace(
        db, user.id, payload.name, payload.description
    )
    if not created:
        raise ApiError(
            status_code=409,
            code="conflict",
            message="A workspace with this name already exists",
        )
    return CreateWorkspaceResponse(workspace=workspace)


@router.get("/{workspace_id}", response_model=GetWorkspaceResponse)
def get_workspace(workspace_id: str, db: Db, user: User) -> GetWorkspaceResponse:
    row = service.get_workspace(db, workspace_id)
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Workspace not found")
    _require_owner(row, user)
    return GetWorkspaceResponse(
        workspace=service.row_to_workspace(
            row, docs=service.get_workspace_docs(db, workspace_id)
        ),
        data=_empty_workspace_data(),
    )


@router.patch("/{workspace_id}", status_code=204)
def update_workspace(
    workspace_id: str, payload: PatchWorkspace, db: Db, user: User
) -> None:
    row = service.update_workspace(
        db, workspace_id, payload.model_dump(exclude_none=True)
    )
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Workspace not found")
    _require_owner(row, user)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str, db: Db, user: User) -> None:
    row = service.get_workspace(db, workspace_id)
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Workspace not found")
    _require_owner(row, user)
    service.delete_workspace(db, workspace_id)
