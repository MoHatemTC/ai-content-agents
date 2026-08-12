"""Integration tests for M5 Generation endpoints.

Tests /generate/questions, /generate/test-help, /generate/flashcards,
/generate/study-plan, /generate/revision.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.generation import service as gen_service
from backend.main import create_app
from src.testing.compliant import Reply
from src.validation.review_schema import RunStatus
from src.validation.store import PlatformStore
from tests.supabase_test_helpers import make_settings, make_token


@pytest.fixture
def gen_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_gen.db")
    chroma_dir = str(tmp_path / "test_gen_chroma")
    settings = make_settings(tmp_path, platform_db_path=db_file, chroma_dir=chroma_dir)
    app = create_app(settings)
    with TestClient(app) as client:
        # 1. Authenticate with a Supabase access token
        token = make_token()
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
                    b"Mitochondria are the organelles that produce most of the cell's supply of "
                    b"adenosine triphosphate, the molecule cells use as a source of chemical energy. "
                    b"Photosynthesis is the process by which green plants and certain other organisms "
                    b"transform light energy into chemical energy. During photosynthesis in green plants "
                    b"light energy is captured and used to convert water, carbon dioxide and minerals "
                    b"into oxygen and energy-rich organic compounds. Cells divide to reproduce and grow.",
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
    assert all(q["type"] == "MCQ" for q in data["questions"])


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


# --------------------------------------------------------------------------- #
# Parity with the orchestrator path
#
# The guards in docs/agent-parity.md are all reached when the agents are driven
# from Streamlit or the orchestrator. These two tests pin the same guarantees
# for the FastAPI path, where the React UI drives them.
# --------------------------------------------------------------------------- #


class _InventingClient:
    """A gateway double that cites a chunk id which is not in the context.

    Mirrors ``CompliantAgentsClient``'s shape, but answers with a fabricated
    ``segment_id``. ``verify_references`` is set membership over the retrieved
    chunk ids, so this is exactly what it exists to catch.
    """

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs: object) -> Reply:
        questions = [
            {
                "question": "Which organelle produces ATP?",
                "options": ["Nucleus", "Mitochondria", "Ribosome", "Golgi"],
                "correct_answer": "Mitochondria",
                "rationale": "Mitochondria produce most of the cell's ATP.",
                "difficulty": "intermediate",
                "type": "mcq",
                "references": [
                    {
                        "segment_id": "chunk-that-was-never-retrieved",
                        "text": "Mitochondria produce most of the cell's ATP.",
                    }
                ],
            }
        ]
        return Reply(json.dumps({"questions": questions, "requires_human_review": True}))


class _ExplodingClient:
    """A gateway double that fails the way a saturated provider does."""

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs: object) -> Reply:
        raise RuntimeError("gateway exploded")


def test_generate_questions_rejects_invented_citations(
    gen_app_client, tmp_path, monkeypatch
):
    """An invented segment_id must not reach the UI as a grounded question.

    The chat path passes ``context=`` and so verifies citations; before this
    fix the generation path passed only a string, which left
    ``_enforce_grounding`` switched off for question bank and test help.
    """
    client, token, ws_id = gen_app_client
    monkeypatch.setattr(
        gen_service, "_get_llm_client", lambda for_study=False: _InventingClient()
    )

    resp = client.post(
        "/generate/questions",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "count": 1,
            "difficulty": "Intermediate",
            "types": ["MCQ"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ungrounded_reply"


class _UnreadableClient:
    """A gateway double whose reply never becomes an object."""

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs: object) -> Reply:
        return Reply("I'd be happy to help! Here are your questions:")


def test_unreadable_reply_is_not_reported_as_ungrounded(
    gen_app_client, monkeypatch
):
    """A reply that never parsed was not "ungrounded" - it was never read.

    Both causes raise ValueError out of the agent, and mapping them together
    told a learner their question could not be grounded in this workspace when
    the model had actually returned prose instead of JSON.
    """
    client, token, ws_id = gen_app_client
    monkeypatch.setattr(
        gen_service, "_get_llm_client", lambda for_study=False: _UnreadableClient()
    )

    resp = client.post(
        "/generate/questions",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "count": 1,
            "difficulty": "Intermediate",
            "types": ["MCQ"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "invalid_model_reply"


def test_failed_generation_is_recorded_not_lost(gen_app_client, tmp_path, monkeypatch):
    """A run that never produced an output still belongs in History."""
    client, token, ws_id = gen_app_client
    monkeypatch.setattr(
        gen_service, "_get_llm_client", lambda for_study=False: _ExplodingClient()
    )

    # The gateway failure still reaches the catch-all handler (a 500 envelope
    # in a real server; TestClient re-raises it). What must not happen is the
    # run disappearing with it.
    with pytest.raises(RuntimeError, match="gateway exploded"):
        client.post(
            "/generate/questions",
            json={
                "workspaceId": ws_id,
                "documentIds": [],
                "model": "gemini",
                "count": 1,
                "difficulty": "Intermediate",
                "types": ["MCQ"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    store = PlatformStore(str(tmp_path / "test_gen.db"))
    failures = store.list_agent_runs(status=RunStatus.FAILURE)
    assert failures, "the failed run was not recorded"
    assert failures[0].agent_name == "question_bank_agent"
    assert "gateway exploded" in (failures[0].error or "")
