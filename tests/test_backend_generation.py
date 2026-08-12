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
from src.study.grounding import DEFAULT_TOP_K
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


# --------------------------------------------------------------------------- #
# Parity with the study lane's own grounding decisions
#
# src/study/grounding.py is not reachable from backend.main - the FastAPI path
# reimplements retrieval inline in this module, and the two copies drifted:
# every build_grounded_context call here used the search lane's default top_k
# (5) instead of the study lane's DEFAULT_TOP_K (12, "12 fills it (~23K)"),
# and study plan/revision built their query from a fixed literal rather than
# what the learner actually asked for. These pin the fix, not the endpoints'
# happy path, which the tests above already cover.
#
# top_k=12 is not a study-lane-only decision: src/app.py's ground() is the
# single retrieval helper behind every Streamlit page, so question bank and
# test help retrieve 12 passages there too. This module's generate_questions_
# service had drifted to the search lane's default of 5, same as the three
# study endpoints - it is included below for that reason, not because it
# shares the study agents' schema.
# --------------------------------------------------------------------------- #


def _spy_on_grounding(monkeypatch) -> list[dict]:
    """Record every build_grounded_context call while still executing it.

    A spy rather than a stub: the fixture's tiny document has real chunks to
    retrieve, and the compliant test client needs real grounded content to
    answer from, so the call must go through.
    """
    calls: list[dict] = []
    real = gen_service.build_grounded_context

    def spy(**kwargs: object) -> object:
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(gen_service, "build_grounded_context", spy)
    return calls


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/generate/flashcards", {"count": 4}),
        ("/generate/study-plan", {"weeks": 2, "hoursPerWeek": 5}),
        ("/generate/revision", {"topics": ["Mitochondria"]}),
        (
            "/generate/questions",
            {"count": 1, "difficulty": "Intermediate", "types": ["MCQ"]},
        ),
        (
            "/generate/test-help",
            {"count": 1, "difficulty": "Intermediate", "options": {}},
        ),
    ],
)
def test_generations_use_the_study_lanes_wider_top_k(
    gen_app_client, monkeypatch, path, payload
):
    """Every grounded generation endpoint retrieves DEFAULT_TOP_K passages.

    Not the search lane's default of 5 - src/study/grounding.py measured that
    a real textbook needs 12 to fill the prompt's own content budget, and
    src/app.py's ground() applies that figure to every Streamlit page alike.
    """
    client, token, ws_id = gen_app_client
    calls = _spy_on_grounding(monkeypatch)

    resp = client.post(
        path,
        json={"workspaceId": ws_id, "documentIds": [], "model": "gemini", **payload},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert calls, "build_grounded_context was never called"
    assert calls[0]["top_k"] == DEFAULT_TOP_K


def test_revision_retrieves_for_the_topics_the_learner_picked(
    gen_app_client, monkeypatch
):
    """The revision query names the learner's topics, not a fixed literal.

    Before this fix, every revision request retrieved for the literal
    "revision topics summary key ideas" regardless of what was asked for, and
    only filtered request.topics against the resulting content afterwards -
    so the passages the sheet was built from could be unrelated to what was
    picked.
    """
    client, token, ws_id = gen_app_client
    calls = _spy_on_grounding(monkeypatch)

    resp = client.post(
        "/generate/revision",
        json={
            "workspaceId": ws_id,
            "documentIds": [],
            "model": "gemini",
            "topics": ["Mitochondria", "Photosynthesis"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert calls[0]["query"] == "Mitochondria Photosynthesis"


def test_revision_falls_back_to_a_topic_query_when_none_were_picked(
    gen_app_client, monkeypatch
):
    """No topics named still retrieves for something on-topic, not blank."""
    client, token, ws_id = gen_app_client
    calls = _spy_on_grounding(monkeypatch)

    resp = client.post(
        "/generate/revision",
        json={"workspaceId": ws_id, "documentIds": [], "model": "gemini", "topics": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert calls[0]["query"].strip() != ""


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/generate/flashcards", {"count": 4}),
        ("/generate/study-plan", {"weeks": 2, "hoursPerWeek": 5}),
        ("/generate/revision", {"topics": ["Mitochondria"]}),
        (
            "/generate/questions",
            {"count": 1, "difficulty": "Intermediate", "types": ["MCQ"]},
        ),
        (
            "/generate/test-help",
            {"count": 1, "difficulty": "Intermediate", "options": {}},
        ),
    ],
)
def test_generations_cap_content_before_prompting(
    gen_app_client, monkeypatch, path, payload
):
    """The 24K content ceiling applies here too, not only in the study lane.

    src/study/grounding.py caps as_prompt_content() before it reaches a
    prompt; these services called as_prompt_content() directly with no cap.
    Question bank and test help are included because
    question_agent_base._build_prompt renders `content` regardless of
    `context`, so - unlike mentor/concept - a capped string handed to
    `content=` is what the model actually sees; see the comment in
    generate_questions_service. Spying on cap_content (rather than
    constructing an oversized corpus) checks the wiring without duplicating
    test_content_is_capped_even_if_retrieval_returns_a_lot, which already
    pins cap_content's own behaviour.
    """
    client, token, ws_id = gen_app_client
    calls: list[str] = []
    real_cap = gen_service.cap_content

    def spy(content: str, *args: object, **kwargs: object) -> str:
        calls.append(content)
        return real_cap(content, *args, **kwargs)

    monkeypatch.setattr(gen_service, "cap_content", spy)

    resp = client.post(
        path,
        json={"workspaceId": ws_id, "documentIds": [], "model": "gemini", **payload},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert calls, "cap_content was never called before prompting"
