"""Request/response schemas for the workspaces endpoints.

Shapes match Sensei-AI ``src/types/api/workspace.contracts.ts`` and the
``Workspace``/``WorkspaceData`` domain types.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Accent = Literal["primary", "info", "success", "warning"]


class Workspace(BaseModel):
    id: str
    name: str
    subject: str
    description: str | None = None
    docs: int = 0
    assets: int = 0
    pendingReview: int = 0
    accent: Accent


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str | None = None


class CreateWorkspaceResponse(BaseModel):
    workspace: Workspace


class GetWorkspacesResponse(BaseModel):
    workspaces: list[Workspace]


class WorkspaceData(BaseModel):
    docs: list
    questions: list
    flashcards: list
    chats: list
    history: list
    weakTopics: list
    audit: list


class GetWorkspaceResponse(BaseModel):
    workspace: Workspace
    data: WorkspaceData


class PatchWorkspace(BaseModel):
    name: str | None = None
    description: str | None = None
    subject: str | None = None
