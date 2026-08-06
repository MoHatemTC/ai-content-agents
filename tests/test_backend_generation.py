"""Integration tests for M5 Generation endpoints.

Tests /generate/questions, /generate/test-help, /generate/flashcards,
/generate/study-plan, /generate/revision.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


@pytest.fixture
def gen_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_gen.db")
    chroma_dir = str(tmp_path / "test_gen_chroma")
    settings = Settings(
        platform_db_path=db_file,
        chroma_dir=chroma_dir,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # 1. Login
        login_resp = client.post(
            "/auth/login",
            json={"email": "student@demo.com", "password": "student"},
        )
        token = login_resp.json()["session"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Create workspace
        ws_resp = client.post(
            "/workspaces",
            json={"name": "Biology Workspace", "description": "Gen test"},
            headers=auth_headers,
        )
        ws_id = ws_resp.json()["workspace"]["id"]

        # 3. Upload & ingest document
        upload_resp = client.post(
            "/upload",
            data={"workspace_id": ws_id},
            files={
                "file": (
                    "biology.txt",
                    b"Mitochondria is the powerhouse of the cell. Photosynthesis converts sunlight into energy.",
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


def test_generation_requires_auth(gen_app_client):
    client, _, ws_id = gen_app_client
    resp = client.post(
        "/generate/questions",
        json={"workspaceId": ws_id, "documentIds": []},
    )
    assert resp.status_code == 401


def test_generate_questions_success(gen_app_client):
    client, token, ws_id = gen_app_client
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/generate/questions",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "count": 3,
            "difficulty": "Intermediate",
            "types": ["MCQ"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "question_bank"
    assert "generationId" in data
    assert len(data["questions"]) > 0
    assert data["grounding_score"] >= 0.0


def test_generate_test_help_success(gen_app_client):
    client, token, ws_id = gen_app_client
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/generate/test-help",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "count": 2,
            "difficulty": "Beginner",
            "options": {"durationMinutes": 45},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "question_bank"
    assert len(data["questions"]) > 0


def test_generate_flashcards_success(gen_app_client):
    client, token, ws_id = gen_app_client
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/generate/flashcards",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "count": 4,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "flashcards"
    assert len(data["flashcards"]) > 0
    assert "front" in data["flashcards"][0]
    assert "back" in data["flashcards"][0]


def test_generate_study_plan_success(gen_app_client):
    client, token, ws_id = gen_app_client
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/generate/study-plan",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "weeks": 2,
            "hoursPerWeek": 5,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "study_plan"
    assert "sections" in data
    assert len(data["sections"]) > 0


def test_generate_revision_sheet_success(gen_app_client):
    client, token, ws_id = gen_app_client
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/generate/revision",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "topics": ["Mitochondria", "Photosynthesis"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "revision_sheet"
    assert "sections" in data
    assert len(data["weakTopics"]) > 0
