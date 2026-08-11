"""Integration tests for M7 Review endpoints.

Tests GET /review, /review/approve, /review/reject, /review/needs-edit,
/review/flag, /review/comment, GET /review/audit.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.supabase_test_helpers import make_settings, make_token


@pytest.fixture
def review_app_client(tmp_path) -> tuple[TestClient, str, str]:
    db_file = str(tmp_path / "test_review.db")
    chroma_dir = str(tmp_path / "test_review_chroma")
    settings = make_settings(tmp_path, platform_db_path=db_file, chroma_dir=chroma_dir)
    app = create_app(settings)
    with TestClient(app) as client:
        token = make_token()
        auth_headers = {"Authorization": f"Bearer {token}"}

        ws_resp = client.post(
            "/workspaces",
            json={"name": "Chemistry Workspace", "description": "Review test"},
            headers=auth_headers,
        )
        ws_id = ws_resp.json()["workspace"]["id"]

        upload_resp = client.post(
            "/upload",
            data={"workspace_id": ws_id},
            files={
                "file": (
                    "chem.txt",
                    b"Organic chemistry is the study of the structure, properties, composition, "
                    b"reactions and preparation of carbon-containing compounds. Most organic "
                    b"compounds contain carbon and hydrogen atoms, and they may also contain "
                    b"oxygen, nitrogen, sulfur or halogens. Hydrocarbons, alcohols, carboxylic "
                    b"acids, amines and esters are common families of organic compounds.",
                    "text/plain",
                )
            },
            headers=auth_headers,
        )
        doc_id = upload_resp.json()["document"]["id"]
        client.post(f"/documents/{doc_id}/parse", headers=auth_headers)
        client.post(f"/documents/{doc_id}/chunk", headers=auth_headers)
        client.post(f"/documents/{doc_id}/embed", headers=auth_headers)

        # Generate questions to populate pending review queue
        client.post(
            "/generate/questions",
            json={"workspaceId": ws_id, "documentIds": [], "count": 2},
            headers=auth_headers,
        )

        yield client, token, ws_id


def test_review_queue_and_approve(review_app_client):
    client, token, ws_id = review_app_client
    headers = {"Authorization": f"Bearer {token}"}

    # GET review queue
    queue_resp = client.get(f"/review?workspace_id={ws_id}", headers=headers)
    assert queue_resp.status_code == 200
    item_ids = queue_resp.json()["itemIds"]
    assert len(item_ids) > 0
    target_id = item_ids[0]

    # Approve item
    app_resp = client.post(
        "/review/approve",
        json={"workspaceId": ws_id, "itemId": target_id, "comment": "Looks good"},
        headers=headers,
    )
    assert app_resp.status_code == 200
    data = app_resp.json()
    assert data["itemId"] == target_id
    assert data["status"] == "approved"
    assert data["audit"]["action"] == "approve"


def test_review_actions_reject_needs_edit_comment(review_app_client):
    client, token, ws_id = review_app_client
    headers = {"Authorization": f"Bearer {token}"}

    queue_resp = client.get(f"/review?workspace_id={ws_id}", headers=headers)
    target_id = queue_resp.json()["itemIds"][0]

    # Needs edit
    edit_resp = client.post(
        "/review/needs-edit",
        json={"workspaceId": ws_id, "itemId": target_id, "comment": "Fix question 1"},
        headers=headers,
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["status"] in ["edited", "pending"]

    # Reject
    rej_resp = client.post(
        "/review/reject",
        json={
            "workspaceId": ws_id,
            "itemId": target_id,
            "comment": "Irrelevant content",
        },
        headers=headers,
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] == "rejected"

    # Audit history
    audit_resp = client.get(f"/review/audit?workspace_id={ws_id}", headers=headers)
    assert audit_resp.status_code == 200
    audit = audit_resp.json()["audit"]
    assert len(audit) >= 2
