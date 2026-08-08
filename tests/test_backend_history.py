"""Integration tests for M7 History endpoints.

Tests GET /history (list) and POST /history (record), including idempotency and
per-workspace scoping.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.supabase_test_helpers import make_settings, make_token


@pytest.fixture
def history_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_history.db")
    settings = make_settings(tmp_path, platform_db_path=db_file)
    app = create_app(settings)
    with TestClient(app) as client:
        token = make_token()
        headers = {"Authorization": f"Bearer {token}"}
        ws_resp = client.post(
            "/workspaces",
            json={"name": "History Workspace", "description": "History test"},
            headers=headers,
        )
        ws_id = ws_resp.json()["workspace"]["id"]
        yield client, token, ws_id


def _row(overrides: dict | None = None) -> dict:
    base = {
        "id": "gen-abc123",
        "date": "2026-08-08 10:30",
        "agent": "Question Bank",
        "doc": "Biology Notes",
        "status": "Completed",
        "quality": 9.2,
        "review": "Pending",
        "items": 5,
    }
    base.update(overrides or {})
    return base


def test_history_list_empty_and_append(history_app_client):
    client, token, ws_id = history_app_client
    headers = {"Authorization": f"Bearer {token}"}

    list_resp = client.get(f"/history?workspace_id={ws_id}", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["history"] == []

    append_resp = client.post(
        "/history",
        json={"workspaceId": ws_id, "row": _row()},
        headers=headers,
    )
    assert append_resp.status_code == 200
    assert append_resp.json()["id"] == "gen-abc123"

    list_resp = client.get(f"/history?workspace_id={ws_id}", headers=headers)
    assert list_resp.status_code == 200
    history = list_resp.json()["history"]
    assert len(history) == 1
    assert history[0]["agent"] == "Question Bank"
    assert history[0]["doc"] == "Biology Notes"
    assert history[0]["items"] == 5


def test_history_append_is_idempotent(history_app_client):
    client, token, ws_id = history_app_client
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(2):
        resp = client.post(
            "/history",
            json={"workspaceId": ws_id, "row": _row()},
            headers=headers,
        )
        assert resp.status_code == 200

    list_resp = client.get(f"/history?workspace_id={ws_id}", headers=headers)
    history = list_resp.json()["history"]
    assert len(history) == 1

    client.post(
        "/history",
        json={"workspaceId": ws_id, "row": _row({"items": 7, "chatId": "chat-x1"})},
        headers=headers,
    )
    history = client.get(f"/history?workspace_id={ws_id}", headers=headers).json()[
        "history"
    ]
    assert len(history) == 1
    assert history[0]["items"] == 7
    assert history[0]["chatId"] == "chat-x1"


def test_history_scoped_to_other_workspace(history_app_client):
    client, token, ws_id = history_app_client
    headers = {"Authorization": f"Bearer {token}"}

    other = client.post(
        "/workspaces",
        json={"name": "Other", "description": "scoped"},
        headers=headers,
    ).json()["workspace"]["id"]

    client.post(
        "/history",
        json={"workspaceId": other, "row": _row()},
        headers=headers,
    )

    assert client.get(f"/history?workspace_id={ws_id}", headers=headers).json()[
        "history"
    ] == []
    assert len(
        client.get(f"/history?workspace_id={other}", headers=headers).json()["history"]
    ) == 1
