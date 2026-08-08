"""Integration tests for M8 Export endpoints.

Tests POST /exports, GET /exports, and human-review export gate assertion.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.supabase_test_helpers import make_settings, make_token


@pytest.fixture
def export_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_export.db")
    chroma_dir = str(tmp_path / "test_export_chroma")
    settings = make_settings(tmp_path, platform_db_path=db_file, chroma_dir=chroma_dir)
    app = create_app(settings)
    with TestClient(app) as client:
        token = make_token()
        auth_headers = {"Authorization": f"Bearer {token}"}

        ws_resp = client.post(
            "/workspaces",
            json={"name": "History Workspace", "description": "Export test"},
            headers=auth_headers,
        )
        ws_id = ws_resp.json()["workspace"]["id"]

        upload_resp = client.post(
            "/upload",
            data={"workspace_id": ws_id},
            files={
                "file": (
                    "history.txt",
                    b"World War II was a global conflict that lasted from 1939 until 1945, "
                    b"involving the great powers of the time and almost every country in the "
                    b"world. The war was fought between the Axis powers and the Allies across "
                    b"multiple theatres, including Europe, the Pacific, Africa and Asia. Key "
                    b"events include the invasion of Poland, the attack on Pearl Harbor and the "
                    b"atomic bombings of Japan.",
                    "text/plain",
                )
            },
            headers=auth_headers,
        )
        doc_id = upload_resp.json()["document"]["id"]
        client.post(f"/documents/{doc_id}/parse", headers=auth_headers)
        client.post(f"/documents/{doc_id}/chunk", headers=auth_headers)
        client.post(f"/documents/{doc_id}/embed", headers=auth_headers)

        gen_resp = client.post(
            "/generate/questions",
            json={"workspaceId": ws_id, "documentIds": [], "count": 2},
            headers=auth_headers,
        )
        gen_id = gen_resp.json()["generationId"]

        yield client, token, ws_id, gen_id


def test_export_unapproved_item_blocks_with_403(export_app_client):
    client, token, ws_id, gen_id = export_app_client
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt export before approval -> 403 not_exportable
    resp = client.post(
        "/exports",
        json={"workspaceId": ws_id, "output_id": gen_id, "format": "json"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_exportable"


def test_export_approved_item_succeeds(export_app_client):
    client, token, ws_id, gen_id = export_app_client
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Approve item
    client.post(
        "/review/approve",
        json={"workspaceId": ws_id, "itemId": gen_id, "comment": "Approved for export"},
        headers=headers,
    )

    # 2. Export JSON
    json_resp = client.post(
        "/exports",
        json={"workspaceId": ws_id, "output_id": gen_id, "format": "json"},
        headers=headers,
    )
    assert json_resp.status_code == 200
    assert "application/json" in json_resp.headers["content-type"]
    assert b"outputs" in json_resp.content

    # 3. Export Markdown
    md_resp = client.post(
        "/exports",
        json={"workspaceId": ws_id, "output_id": gen_id, "format": "markdown"},
        headers=headers,
    )
    assert md_resp.status_code == 200
    assert "text/markdown" in md_resp.headers["content-type"]

    # 4. List exports
    list_resp = client.get(f"/exports?workspace_id={ws_id}", headers=headers)
    assert list_resp.status_code == 200
    assert "exports" in list_resp.json()
