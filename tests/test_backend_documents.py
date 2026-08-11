"""Tests for the M3 documents & upload pipeline."""

from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.supabase_test_helpers import make_settings, make_token


def _client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path, chroma_dir="")))


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


def _create_workspace(client: TestClient, token: str, name: str = "Biology") -> dict:
    response = client.post("/workspaces", json={"name": name}, headers=_auth(token))
    return response.json()["workspace"]


LONG_TEXT = (
    "Mitochondria are the organelles responsible for aerobic respiration in "
    "eukaryotic cells. They convert chemical energy from glucose into ATP, the "
    "molecule cells use to power their metabolism. This document describes how "
    "the electron transport chain drives oxidative phosphorylation and why this "
    "process is essential for multicellular life."
)


def _upload(
    client: TestClient,
    token: str,
    workspace_id: str,
    filename: str = "notes.txt",
    content: bytes = LONG_TEXT.encode(),
) -> dict:
    response = client.post(
        "/documents/upload",
        data={"workspace_id": workspace_id},
        files={"file": (filename, content, "text/plain")},
        headers=_auth(token),
    )
    return response


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    page_texts = (
        "Photosynthesis converts light energy into chemical energy stored as "
        "glucose. Plants use chlorophyll pigments to capture photons and drive "
        "the light-dependent reactions that produce ATP and NADPH."
    )
    for text in (page_texts, page_texts):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


# --------------------------------------------------------------------------- #
# Auth gating
# --------------------------------------------------------------------------- #


def test_upload_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/documents/upload",
            data={"workspace_id": "ws"},
            files={"file": ("a.txt", b"content")},
        )

    assert response.status_code == 401


def test_list_documents_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/documents?workspace_id=ws")

    assert response.status_code == 401


def test_parse_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/documents/abc/parse")

    assert response.status_code == 401


def test_notes_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.patch("/documents/abc/notes", json={"notes": "hi"})

    assert response.status_code == 401


def test_delete_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/documents/abc")

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def test_upload_returns_document_and_storage_path(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _upload(client, token, workspace["id"])

    assert response.status_code == 201
    body = response.json()
    document = body["document"]
    assert document["title"] == "notes"
    assert document["kind"] == "TXT"
    assert document["status"] == "Ready"
    assert document["tags"] == []
    assert document["chunks"] == []
    assert document["sizeBytes"] == len(LONG_TEXT.encode())
    assert document["size"] == f"{max(1, round(len(LONG_TEXT.encode()) / 1024))} KB"
    assert body["storage_path"].startswith(f"{workspace['id']}/")
    assert body["storage_path"].endswith("notes.txt")


def test_upload_markdown_is_kind_txt(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _upload(
            client,
            token,
            workspace["id"],
            filename="notes.md",
            content=b"# Title\n\nbody text",
        )

    assert response.status_code == 201
    assert response.json()["document"]["kind"] == "TXT"


def test_upload_unsupported_kind_returns_422(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _upload(
            client, token, workspace["id"], filename="deck.pptx", content=b"x"
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_over_size_limit_returns_413(tmp_path) -> None:
    settings = make_settings(tmp_path, chroma_dir="", max_upload_bytes=10)
    with TestClient(create_app(settings)) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _upload(client, token, workspace["id"], content=b"x" * 11)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_upload_to_unknown_workspace_returns_404(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = _upload(client, token, "no-such-workspace")

    assert response.status_code == 404


def test_upload_to_other_users_workspace_returns_403(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create_workspace(client, student_token)
        response = _upload(client, reviewer_token, workspace["id"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_workspace_docs_count_is_real(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        _upload(client, token, workspace["id"])
        _upload(client, token, workspace["id"], filename="second.txt")

        listed = client.get("/workspaces", headers=_auth(token)).json()["workspaces"]
        fetched = client.get(
            f"/workspaces/{workspace['id']}", headers=_auth(token)
        ).json()["workspace"]

    assert next(w for w in listed if w["id"] == workspace["id"])["docs"] == 2
    assert fetched["docs"] == 2


# --------------------------------------------------------------------------- #
# List / chunks / notes / delete
# --------------------------------------------------------------------------- #


def test_list_documents_orders_newest_first(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        first = _upload(client, token, workspace["id"]).json()["document"]
        second = _upload(client, token, workspace["id"], filename="second.txt").json()[
            "document"
        ]

        response = client.get(
            f"/documents?workspace_id={workspace['id']}", headers=_auth(token)
        )

    assert response.status_code == 200
    ids = [d["id"] for d in response.json()["documents"]]
    assert ids == [second["id"], first["id"]]


def test_list_documents_requires_workspace_id(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = client.get("/documents", headers=_auth(token))

    assert response.status_code == 422


def test_cannot_list_other_users_documents(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create_workspace(client, student_token)
        response = client.get(
            f"/documents?workspace_id={workspace['id']}", headers=_auth(reviewer_token)
        )

    assert response.status_code == 403


def test_notes_patch_round_trips(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(client, token, workspace["id"]).json()["document"]
        response = client.patch(
            f"/documents/{document['id']}/notes",
            json={"notes": "Remember the electron transport chain"},
            headers=_auth(token),
        )
        listed = client.get(
            f"/documents?workspace_id={workspace['id']}", headers=_auth(token)
        ).json()["documents"]

    assert response.status_code == 204
    assert listed[0]["notes"] == "Remember the electron transport chain"


def test_delete_document_removes_it(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(client, token, workspace["id"]).json()["document"]
        deleted = client.delete(f"/documents/{document['id']}", headers=_auth(token))
        listed = client.get(
            f"/documents?workspace_id={workspace['id']}", headers=_auth(token)
        ).json()["documents"]

    assert deleted.status_code == 204
    assert listed == []


# --------------------------------------------------------------------------- #
# Pipeline: parse → chunk → embed
# --------------------------------------------------------------------------- #


def test_full_pipeline_on_txt(tmp_path, monkeypatch) -> None:
    # Pinned rather than inherited. backend/main.py calls load_dotenv at import,
    # so a developer's RETRIEVAL_EMBEDDER=onnx leaks in and this assertion fails
    # on their machine while passing in CI, which has no .env. Asserting on the
    # embedder means choosing it - the same hermeticity PR #28 gave the main
    # suite. hashing also keeps the test offline: onnx downloads ~80 MB.
    monkeypatch.setenv("RETRIEVAL_EMBEDDER", "hashing")
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(client, token, workspace["id"]).json()["document"]

        parsed = client.post(f"/documents/{document['id']}/parse", headers=_auth(token))
        assert parsed.status_code == 200
        parse_body = parsed.json()
        assert parse_body["documentId"] == document["id"]
        assert parse_body["pages"] is None
        assert parse_body["text_length"] > 100

        chunked = client.post(
            f"/documents/{document['id']}/chunk", headers=_auth(token)
        )
        assert chunked.status_code == 200
        chunks = chunked.json()["chunks"]
        assert len(chunks) == 1
        assert chunks[0]["id"] == f"{document['id']}-c0000"
        assert chunks[0]["tokens"] > 0
        assert chunks[0]["text"]
        assert chunks[0]["page"] is None

        embedded = client.post(
            f"/documents/{document['id']}/embed", headers=_auth(token)
        )
        assert embedded.status_code == 200
        embed_body = embedded.json()
        assert embed_body["documentId"] == document["id"]
        assert embed_body["embedded"] == len(chunks)
        assert embed_body["model"] == "hashing"

        chunks_response = client.get(
            f"/documents/{document['id']}/chunks", headers=_auth(token)
        )
        assert chunks_response.status_code == 200
        assert chunks_response.json()["chunks"] == chunks

        listed = client.get(
            f"/documents?workspace_id={workspace['id']}", headers=_auth(token)
        ).json()["documents"]
        assert listed[0]["status"] == "Ready"


def test_chunk_before_parse_returns_409(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(client, token, workspace["id"]).json()["document"]
        response = client.post(
            f"/documents/{document['id']}/chunk", headers=_auth(token)
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_embed_before_chunk_returns_409(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(client, token, workspace["id"]).json()["document"]
        client.post(f"/documents/{document['id']}/parse", headers=_auth(token))
        response = client.post(
            f"/documents/{document['id']}/embed", headers=_auth(token)
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_parse_rejects_low_quality_content(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _upload(
            client, token, workspace["id"], content=b"a a a a a a a a a a"
        ).json()["document"]
        response = client.post(
            f"/documents/{document['id']}/parse", headers=_auth(token)
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_document_returns_404(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = client.post("/documents/nope/parse", headers=_auth(token))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cannot_parse_other_users_document(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create_workspace(client, student_token)
        document = _upload(client, student_token, workspace["id"]).json()["document"]
        response = client.post(
            f"/documents/{document['id']}/parse", headers=_auth(reviewer_token)
        )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# PDF pipeline (real page numbers)
# --------------------------------------------------------------------------- #


def test_pdf_pipeline_reports_real_pages(tmp_path) -> None:
    pdf = _pdf_bytes()
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _upload(
            client, token, workspace["id"], filename="photosynthesis.pdf", content=pdf
        )
        assert response.status_code == 201
        document = response.json()["document"]
        assert document["kind"] == "PDF"

        parsed = client.post(f"/documents/{document['id']}/parse", headers=_auth(token))
        assert parsed.status_code == 200
        assert parsed.json()["pages"] == 2
        assert parsed.json()["text_length"] > 100

        chunked = client.post(
            f"/documents/{document['id']}/chunk", headers=_auth(token)
        )
        assert chunked.status_code == 200
        pages = {chunk["page"] for chunk in chunked.json()["chunks"]}
        assert pages and pages <= {1, 2}

        embedded = client.post(
            f"/documents/{document['id']}/embed", headers=_auth(token)
        )
        assert embedded.status_code == 200
        assert embedded.json()["embedded"] == len(chunked.json()["chunks"])

        deleted = client.delete(f"/documents/{document['id']}", headers=_auth(token))
        assert deleted.status_code == 204
