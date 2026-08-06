"""FastAPI router for chat endpoints (M6).

Exposes POST /chats, GET /chats, POST /mentor/chat, POST /concept/chat.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.auth.schemas import AuthUser
from backend.chat.schemas import (
    ConceptChatRequest,
    ConceptChatResponse,
    CreateChatRequest,
    CreateChatResponse,
    GetChatsResponse,
    MentorChatRequest,
    MentorChatResponse,
)
from backend.chat.service import (
    create_chat_service,
    list_chats_service,
    send_chat_message_service,
)
from backend.config import Settings
from backend.deps import get_current_user, get_settings, require_workspace_member

router = APIRouter(tags=["chat"])


@router.post("/chats", response_model=CreateChatResponse)
async def create_chat(
    request_body: CreateChatRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CreateChatResponse:
    """Create a new chat session."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return create_chat_service(
        request_body,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
    )


@router.get("/chats", response_model=GetChatsResponse)
async def list_chats(
    workspace_id: Annotated[str, Query(alias="workspace_id")],
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetChatsResponse:
    """List chat sessions and their messages for a workspace."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=workspace_id,
        user=current_user,
    )
    return list_chats_service(
        workspace_id,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
    )


@router.post("/mentor/chat", response_model=MentorChatResponse)
async def mentor_chat(
    request_body: MentorChatRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MentorChatResponse:
    """Send a user message to the Mentor AI agent."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return send_chat_message_service(
        request_body,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
        kind="mentor",
    )


@router.post("/concept/chat", response_model=ConceptChatResponse)
async def concept_chat(
    request_body: ConceptChatRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConceptChatResponse:
    """Send a user message to the Concept AI agent."""
    require_workspace_member(
        db_path=settings.platform_db_path,
        workspace_id=request_body.workspaceId,
        user=current_user,
    )
    return send_chat_message_service(
        request_body,
        user_id=current_user.id,
        db_path=settings.platform_db_path,
        chroma_dir=settings.chroma_dir,
        kind="concept",
    )
