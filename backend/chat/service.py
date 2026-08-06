"""Service layer for chat endpoints (M6).

Handles creating chats, listing chats, sending mentor/concept chat messages,
grounding retrieved chunks, and persisting turns & audit outputs to PlatformStore.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from backend.chat.schemas import (
    ChatCitation,
    ChatSummary,
    CreateChatRequest,
    CreateChatResponse,
    GetChatsResponse,
    MentorChatRequest,
    MentorChatResponse,
    WsChatMessage,
)
from backend.generation.service import _get_llm_client
from backend.search.service import build_grounded_context
from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import InsufficientGroundingError
from src.validation.review_schema import AgentRun, GeneratedOutput, OutputStatus
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_chat_service(
    request: CreateChatRequest,
    *,
    user_id: str,
    db_path: str,
) -> CreateChatResponse:
    """Create a new chat session."""
    chat_id = f"chat-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO chats (id, workspace_id, user_id, kind, title, model, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                request.workspaceId,
                user_id,
                request.kind,
                request.title,
                request.model,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return CreateChatResponse(chatId=chat_id)


def list_chats_service(
    workspace_id: str,
    *,
    user_id: str,
    db_path: str,
) -> GetChatsResponse:
    """List chat sessions and their messages for a workspace."""
    conn = _connect(db_path)
    try:
        chat_rows = conn.execute(
            """
            SELECT id, title, kind, model, created_at
            FROM chats
            WHERE workspace_id = ? AND user_id = ?
            ORDER BY updated_at DESC
            """,
            (workspace_id, user_id),
        ).fetchall()

        chats: list[ChatSummary] = []
        for c_id, title, kind, model, created_at in chat_rows:
            msg_rows = conn.execute(
                """
                SELECT id, role, text, created_at
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY created_at ASC
                """,
                (c_id,),
            ).fetchall()

            messages = [
                WsChatMessage(
                    id=m_id,
                    role=role,
                    text=text,
                    time=m_created[:16].replace("T", " "),
                )
                for m_id, role, text, m_created in msg_rows
            ]

            chats.append(
                ChatSummary(
                    id=c_id,
                    title=title,
                    agent=kind,
                    model=model,
                    date=created_at[:10],
                    messages=messages,
                )
            )

    finally:
        conn.close()

    return GetChatsResponse(chats=chats)


def send_chat_message_service(
    request: MentorChatRequest,
    *,
    user_id: str,
    db_path: str,
    chroma_dir: str,
    kind: str = "mentor",
) -> MentorChatResponse:
    """Process a user chat turn via Mentor or Concept agent, persisting messages and audit records."""
    store = PlatformStore(db_path)
    conn = _connect(db_path)
    try:
        chat_row = conn.execute(
            "SELECT id, workspace_id, title FROM chats WHERE id = ? AND user_id = ?",
            (request.chatId, user_id),
        ).fetchone()

        if not chat_row:
            raise KeyError(f"Chat {request.chatId} not found for this user.")

        now_str = datetime.now(timezone.utc).isoformat()
        user_msg_id = f"m-{uuid4().hex[:8]}"

        # Record user message
        conn.execute(
            """
            INSERT INTO chat_messages (id, chat_id, role, text, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_msg_id, request.chatId, "user", request.message, "[]", now_str),
        )
        conn.commit()
    finally:
        conn.close()

    # Retrieve grounded context
    grounded = build_grounded_context(
        workspace_id=request.workspaceId,
        query=request.message,
        document_ids=request.documentIds if request.documentIds else None,
        chroma_dir=chroma_dir,
    )

    if not grounded.chunks:
        raise InsufficientGroundingError(
            "No relevant document chunks found to ground the answer."
        )

    # Get document titles for citations
    doc_titles: dict[str, str] = {}
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT id, title FROM documents").fetchall()
        doc_titles = {r[0]: r[1] for r in rows}
    finally:
        conn.close()

    client = _get_llm_client(for_study=False)

    if kind == "concept":
        agent = ConceptAgent(client=client, model=request.model)
        concept_output = agent.generate(
            content=grounded,
            user_question=request.message,
            difficulty="intermediate",
            context=grounded,
        )
        reply_text = f"{concept_output.definition}\n\n{concept_output.explanation}"
    else:
        agent = MentorAgent(client=client, model=request.model)
        mentor_output = agent.generate(
            content=grounded,
            user_question=request.message,
            difficulty="intermediate",
            context=grounded,
        )
        reply_text = mentor_output.explanation

    citations: list[ChatCitation] = []
    for chunk in grounded.chunks:
        doc_id = (
            chunk.chunk_id.split("-c")[0] if "-c" in chunk.chunk_id else chunk.chunk_id
        )
        title = doc_titles.get(doc_id, "Document")
        citations.append(
            ChatCitation(
                docId=doc_id,
                docTitle=title,
                page=getattr(chunk, "page", None),
                snippet=chunk.text[:200],
            )
        )

    assistant_msg_id = f"m-{uuid4().hex[:8]}"
    assistant_now = datetime.now(timezone.utc).isoformat()
    citations_json = json.dumps([c.model_dump() for c in citations])

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO chat_messages (id, chat_id, role, text, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                assistant_msg_id,
                request.chatId,
                "assistant",
                reply_text,
                citations_json,
                assistant_now,
            ),
        )
        conn.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (assistant_now, request.chatId),
        )
        conn.commit()
    finally:
        conn.close()

    # Save to PlatformStore
    run = AgentRun(
        agent_name=f"{kind}_agent",
        input_context=f"chat:{request.chatId}",
        source_chunk_ids=grounded.chunk_ids,
        model=request.model,
    )
    run.mark_finished()
    store.save_agent_run(run)

    gen_id = f"gen-{uuid4().hex[:8]}"
    gen_output = GeneratedOutput(
        id=gen_id,
        agent_run_id=run.id,
        output_type=f"{kind}_chat",
        payload={"text": reply_text, "citations": [c.model_dump() for c in citations]},
        schema_name="MentorOutput" if kind == "mentor" else "ConceptOutput",
        validation_passed=True,
        validation_report={"grounded": True},
        status=OutputStatus.PENDING,
    )
    store.save_output(gen_output)

    return MentorChatResponse(
        message=WsChatMessage(
            id=assistant_msg_id,
            role="assistant",
            text=reply_text,
            time=assistant_now[11:16],
        ),
        citations=citations,
    )
