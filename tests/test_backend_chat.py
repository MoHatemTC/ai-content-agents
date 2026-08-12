"""Integration tests for M6 Chat endpoints.

Tests /chats, POST /mentor/chat, POST /concept/chat.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.chat import service as chat_service
from backend.main import create_app
from src.study.grounding import DEFAULT_TOP_K
from tests.supabase_test_helpers import make_settings, make_token


@pytest.fixture
def chat_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_chat.db")
    chroma_dir = str(tmp_path / "test_chat_chroma")
    settings = make_settings(tmp_path, platform_db_path=db_file, chroma_dir=chroma_dir)
    app = create_app(settings)
    with TestClient(app) as client:
        token = make_token()
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
                    b"Newton's laws of motion are three physical laws that together describe the "
                    b"relationship between the motion of an object and the forces acting on it. The "
                    b"first law states that an object at rest stays at rest and an object in motion "
                    b"stays in motion unless acted upon by a net external force. The second law states "
                    b"that the acceleration of an object is directly proportional to the net force "
                    b"acting on it and inversely proportional to its mass. The third law states that "
                    b"every action has an equal and opposite reaction.",
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


def test_chat_citations_carry_the_cited_chunk(chat_app_client):
    """The chunk id has to survive into the citation.

    The prompts tell the model to write segment_ids into its prose, so the UI
    has to match a marker in the reply to the passage it names. Chat used to
    split the id down to its document half (``segment_id.split("-c")[0]``),
    which left nothing to match on - while generation's Citation kept it.
    """
    client, token, ws_id = chat_app_client
    headers = {"Authorization": f"Bearer {token}"}

    chat_id = client.post(
        "/chats",
        json={
            "workspaceId": ws_id,
            "kind": "mentor",
            "title": "Mentor Chat",
            "model": "gemini",
        },
        headers=headers,
    ).json()["chatId"]

    data = client.post(
        "/mentor/chat",
        json={
            "workspaceId": ws_id,
            "chatId": chat_id,
            "message": "Explain Newton's laws",
            "model": "gemini",
        },
        headers=headers,
    ).json()

    citation = data["citations"][0]
    assert citation["chunk"], "the cited chunk id was dropped"
    # Still a chunk id, not the document id it used to be reduced to.
    assert "-c" in citation["chunk"]
    assert citation["chunk"].startswith(citation["docId"])


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


# --------------------------------------------------------------------------- #
# Parity with the study lane's own grounding decisions
#
# src/app.py's ground() is the single retrieval helper behind every Streamlit
# page - mentor and concept included - and it retrieves DEFAULT_TOP_K (12)
# passages, not the search lane's default of 5. This endpoint had drifted
# back to 5. See tests/test_backend_generation.py for the matching gap on the
# generation endpoints, and its comment on why content is not capped here:
# explanation_agent_base.generate() lets `context` override `content` for the
# prompt whenever both are supplied, which they always are on this path.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["/mentor/chat", "/concept/chat"])
def test_chat_uses_the_study_lanes_wider_top_k(chat_app_client, monkeypatch, path):
    client, token, ws_id = chat_app_client
    headers = {"Authorization": f"Bearer {token}"}
    kind = "mentor" if path == "/mentor/chat" else "concept"

    chat_id = client.post(
        "/chats",
        json={"workspaceId": ws_id, "kind": kind, "title": "t", "model": "gemini"},
        headers=headers,
    ).json()["chatId"]

    calls: list[dict] = []
    real = chat_service.build_grounded_context

    def spy(**kwargs: object) -> object:
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(chat_service, "build_grounded_context", spy)

    resp = client.post(
        path,
        json={
            "workspaceId": ws_id,
            "chatId": chat_id,
            "message": "Explain Newton's laws",
            "model": "gemini",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    assert calls, "build_grounded_context was never called"
    assert calls[0]["top_k"] == DEFAULT_TOP_K
