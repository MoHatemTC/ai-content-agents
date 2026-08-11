"""Tests for the M2 workspaces domain."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.supabase_test_helpers import make_settings, make_token


def _client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path)))


STUDENT = {"email": "student@demo.com", "password": "student"}
REVIEWER = {"email": "reviewer@demo.com", "password": "reviewer"}


def _token(client: TestClient, creds: dict) -> str:
    # Distinct Supabase sub per distinct email so "other users" tests see real
    # 403 / 404 scoping instead of colliding on a single platform user. Email is
    # derived from the sub to avoid clashing with the seeded demo users.
    import hashlib

    sub = hashlib.sha1(creds["email"].encode("utf-8")).hexdigest()[:24]
    return make_token(sub=sub, email=f"{sub}@user.test", name=creds["email"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Auth gating
# --------------------------------------------------------------------------- #


def test_workspaces_require_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/workspaces")

    assert response.status_code == 401


def test_create_workspace_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/workspaces", json={"name": "Physics"})

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Create / list
# --------------------------------------------------------------------------- #


def test_create_workspace_returns_201(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = client.post(
            "/workspaces",
            json={"name": "Physics", "description": "Kinematics"},
            headers=_auth(token),
        )

    assert response.status_code == 201
    workspace = response.json()["workspace"]
    assert workspace["name"] == "Physics"
    assert workspace["description"] == "Kinematics"
    assert workspace["subject"] == ""
    assert workspace["docs"] == 0
    assert workspace["assets"] == 0
    assert workspace["pendingReview"] == 0
    assert workspace["accent"] in ("primary", "info", "success", "warning")


def test_list_workspaces_scoped_to_owner(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        client.post(
            "/workspaces", json={"name": "Physics"}, headers=_auth(student_token)
        )

        student_list = client.get("/workspaces", headers=_auth(student_token)).json()
        reviewer_list = client.get("/workspaces", headers=_auth(reviewer_token)).json()

    assert len(student_list["workspaces"]) == 1
    assert len(reviewer_list["workspaces"]) == 0


def test_duplicate_name_returns_409(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        headers = _auth(token)
        client.post("/workspaces", json={"name": "Physics"}, headers=headers)
        duplicate = client.post(
            "/workspaces", json={"name": "physics"}, headers=headers
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


def test_accent_cycles_across_creations(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        headers = _auth(token)
        accents = []
        for i in range(4):
            response = client.post(
                "/workspaces", json={"name": f"Workspace {i}"}, headers=headers
            )
            accents.append(response.json()["workspace"]["accent"])

    assert len(set(accents)) == 4


# --------------------------------------------------------------------------- #
# Get / patch / delete
# --------------------------------------------------------------------------- #


def _create(client: TestClient, token: str, name: str = "Biology") -> dict:
    response = client.post("/workspaces", json={"name": name}, headers=_auth(token))
    return response.json()["workspace"]


def test_get_workspace_returns_empty_data(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create(client, token)
        response = client.get(f"/workspaces/{workspace['id']}", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"]["id"] == workspace["id"]
    assert body["data"] == {
        "docs": [],
        "questions": [],
        "flashcards": [],
        "chats": [],
        "history": [],
        "weakTopics": [],
        "audit": [],
    }


def test_patch_updates_name_and_subject(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create(client, token)
        # The flat patch object, which is what the frontend actually sends:
        # workspace.api.ts does `http.patch(detail(id), patch)`. The nested
        # {id, patch} form is updateWorkspace's TypeScript argument, not the
        # request body - and PatchWorkspace ignored the unknown keys, so
        # exclude_none produced {} and the route returned 204 having changed
        # nothing.
        patch = client.patch(
            f"/workspaces/{workspace['id']}",
            json={"name": "Botany", "subject": "Life science"},
            headers=_auth(token),
        )
        fetched = client.get(f"/workspaces/{workspace['id']}", headers=_auth(token))

    assert patch.status_code == 204
    updated = fetched.json()["workspace"]
    assert updated["name"] == "Botany"
    assert updated["subject"] == "Life science"


def test_patch_unknown_workspace_returns_404(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = client.patch(
            "/workspaces/nope",
            json={"name": "X"},
            headers=_auth(token),
        )

    assert response.status_code == 404


def test_delete_workspace(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create(client, token)
        deleted = client.delete(f"/workspaces/{workspace['id']}", headers=_auth(token))
        fetched = client.get(f"/workspaces/{workspace['id']}", headers=_auth(token))

    assert deleted.status_code == 204
    assert fetched.status_code == 404


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #


def test_cannot_read_other_users_workspace(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create(client, student_token)
        response = client.get(
            f"/workspaces/{workspace['id']}", headers=_auth(reviewer_token)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_cannot_patch_other_users_workspace(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create(client, student_token)
        response = client.patch(
            f"/workspaces/{workspace['id']}",
            json={"id": workspace["id"], "patch": {"name": "Hijacked"}},
            headers=_auth(reviewer_token),
        )

    assert response.status_code == 403


def test_cannot_delete_other_users_workspace(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create(client, student_token)
        response = client.delete(
            f"/workspaces/{workspace['id']}", headers=_auth(reviewer_token)
        )

    assert response.status_code == 403
