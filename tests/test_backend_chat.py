"""Integration tests for M6 Chat endpoints.

Tests /chats, POST /mentor/chat, POST /concept/chat.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


@pytest.fixture
def chat_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_chat.db")
    chroma_dir = str(tmp_path / "test_chat_chroma")
    settings = Settings(
        platform_db_path=db_file,
        chroma_dir=chroma_dir,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        login_resp = client.post(
            "/auth/login",
            json={"email": "student@demo.com", "password": "student"},
        )
        token = login_resp.json()["session"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        ws_resp = client.post(
            "/workspaces",
            json={"name": "Physics Workspace", "description": "Chat test"},
            headers=auth_headers,
        )
        ws_id = ws_resp.json()["workspace"]["id"]

        upload_resp = client.post(
            "/upload",
            data={"workspace_id": ws_id},
            files={
                "file": (
                    "physics.txt",
                    b"Newton's laws of motion govern mechanics.",
                    "text/plain",
                )
            },
            headers=auth_headers,
        )
        doc_id = upload_resp.json()["document"]["id"]
        client.post(f"/documents/{doc_id}/parse", headers=auth_headers)
        client.post(f"/documents/{doc_id}/chunk", headers=auth_headers)
        client.post(f"/documents/{doc_id}/embed", headers=auth_headers)

        yield client, token, ws_id


def test_create_and_list_chats(chat_app_client):
    client, token, ws_id = chat_app_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create chat
    create_resp = client.post(
        "/chats",
        json={
            "workspaceId": ws_id,
            "kind": "mentor",
            "title": "Physics Help",
            "model": "gemini",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    chat_id = create_resp.json()["chatId"]
    assert chat_id.startswith("chat-")

    # List chats
    list_resp = client.get(f"/chats?workspace_id={ws_id}", headers=headers)
    assert list_resp.status_code == 200
    chats = list_resp.json()["chats"]
    assert len(chats) == 1
    assert chats[0]["id"] == chat_id
    assert chats[0]["title"] == "Physics Help"


def test_mentor_chat_message(chat_app_client):
    client, token, ws_id = chat_app_client
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/chats",
        json={
            "workspaceId": ws_id,
            "kind": "mentor",
            "title": "Mentor Chat",
            "model": "gemini",
        },
        headers=headers,
    )
    chat_id = create_resp.json()["chatId"]

    msg_resp = client.post(
        "/mentor/chat",
        json={
            "workspaceId": ws_id,
            "chatId": chat_id,
            "message": "Explain Newton's laws",
            "model": "gemini",
        },
        headers=headers,
    )
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert "message" in data
    assert data["message"]["role"] == "assistant"
    assert len(data["message"]["text"]) > 0
    assert len(data["citations"]) > 0


def test_concept_chat_message(chat_app_client):
    client, token, ws_id = chat_app_client
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/chats",
        json={
            "workspaceId": ws_id,
            "kind": "concept",
            "title": "Concept Chat",
            "model": "gemini",
        },
        headers=headers,
    )
    chat_id = create_resp.json()["chatId"]

    msg_resp = client.post(
        "/concept/chat",
        json={
            "workspaceId": ws_id,
            "chatId": chat_id,
            "message": "Define mechanics",
            "model": "gemini",
        },
        headers=headers,
    )
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert data["message"]["role"] == "assistant"
    assert len(data["message"]["text"]) > 0
