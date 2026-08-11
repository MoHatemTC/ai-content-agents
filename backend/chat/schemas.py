"""Pydantic schemas for the chat milestone (M6).

Matches the contract defined in docs/FASTAPI_INTEGRATION.md and
Sensei-AI src/types/api/chat.contracts.ts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreateChatRequest(BaseModel):
    workspaceId: str
    kind: Literal["mentor", "concept"] = "mentor"
    title: str
    model: str = "gemini"


class CreateChatResponse(BaseModel):
    chatId: str


class ChatCitation(BaseModel):
    docId: str
    docTitle: str
    page: int | None = None
    snippet: str


class WsChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    time: str
    citations: list[ChatCitation] = Field(default_factory=list)


class MentorChatRequest(BaseModel):
    workspaceId: str
    chatId: str
    message: str
    model: str = "gemini"
    documentIds: list[str] = Field(default_factory=list)


class MentorChatResponse(BaseModel):
    message: WsChatMessage
    citations: list[ChatCitation] = Field(default_factory=list)


ConceptChatRequest = MentorChatRequest
ConceptChatResponse = MentorChatResponse


class ChatSummary(BaseModel):
    id: str
    title: str
    agent: str
    model: str
    date: str
    messages: list[WsChatMessage] = Field(default_factory=list)


class GetChatsResponse(BaseModel):
    chats: list[ChatSummary]
