"""Tests for the M4 search/retrieval facade (GET /search)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.search import service as search_service
from backend.search.schemas import SearchResponse
from tests.test_backend_documents import (
    LONG_TEXT,
    REVIEWER,
    STUDENT,
    _auth,
    _client,
    _create_workspace,
    _token,
)

MITO_TEXT = (
    "Mitochondrial metabolism couples the citric acid cycle to oxidative "
    "phosphorylation through the electron transport chain embedded in the inner "
    "membrane. Electrons donated by NADH and FADH2 flow through complexes I, III "
    "and IV, pumping protons into the intermembrane space to establish the "
    "electrochemical gradient that ATP synthase uses to phosphorylate ADP. The "
    "chemiosmotic theory explains how this proton-motive force drives most ATP "
    "production in aerobic cells. Pyruvate from glycolysis enters the matrix via "
    "the pyruvate dehydrogenase complex and is decarboxylated to acetyl coenzyme A."
)

PHOTO_TEXT = (
    "Plant chloroplasts capture photons with chlorophyll pigments arranged in "
    "antenna complexes that transfer excitation energy toward the reaction centre "
    "of photosystem II. There, water is split into molecular oxygen, protons and "
    "electrons, liberating the oxygen we breathe. The electrons travel along the "
    "electron transport chain toward photosystem I, generating ATP along the way, "
    "and ultimately reduce NADP+ to NADPH. Both ATP and NADPH feed the Calvin "
    "cycle, where carbon dioxide is fixed by ribulose bisphosphate carboxylase."
)

LONG_TEXT_MULTI_CHUNK = " ".join([MITO_TEXT, PHOTO_TEXT] * 2)


def _seed(
    client: TestClient,
    token: str,
    workspace_id: str,
    filename: str,
    content: bytes,
) -> dict:
    """Upload + parse + chunk + embed one document, returning its WsDoc."""
    response = client.post(
        "/documents/upload",
        data={"workspace_id": workspace_id},
        files={"file": (filename, content, "text/plain")},
        headers=_auth(token),
    )
    assert response.status_code == 201
    document = response.json()["document"]
    for stage in ("parse", "chunk", "embed"):
        stage_response = client.post(
            f"/documents/{document['id']}/{stage}", headers=_auth(token)
        )
        assert stage_response.status_code == 200, stage
    return document


def _search(client: TestClient, token: str, workspace_id: str, q: str, **params):
    query = {"q": q, "workspace_id": workspace_id, **params}
    return client.get("/search", params=query, headers=_auth(token))


# --------------------------------------------------------------------------- #
# Auth gating & parameters
# --------------------------------------------------------------------------- #


def test_search_requires_auth(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/search", params={"q": "x", "workspace_id": "ws"})

    assert response.status_code == 401


def test_search_requires_query_and_workspace(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        missing_q = client.get(
            "/search", params={"workspace_id": workspace["id"]}, headers=_auth(token)
        )
        missing_workspace = client.get(
            "/search", params={"q": "mitochondria"}, headers=_auth(token)
        )
        bad_limit = _search(client, token, workspace["id"], "mitochondria", limit=0)

    assert missing_q.status_code == 422
    assert missing_q.json()["error"]["code"] == "validation_error"
    assert missing_workspace.status_code == 422
    assert bad_limit.status_code == 422


def test_search_unknown_workspace_returns_404(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        response = _search(client, token, "no-such-workspace", "mitochondria")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_search_other_users_workspace_returns_403(tmp_path) -> None:
    with _client(tmp_path) as client:
        student_token = _token(client, STUDENT)
        reviewer_token = _token(client, REVIEWER)
        workspace = _create_workspace(client, student_token)
        response = _search(client, reviewer_token, workspace["id"], "mitochondria")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


# --------------------------------------------------------------------------- #
# Retrieval behaviour
# --------------------------------------------------------------------------- #


def test_search_empty_workspace_returns_no_results(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _search(client, token, workspace["id"], "mitochondria")

    assert response.status_code == 200
    assert response.json() == {"results": [], "total": 0}


def test_search_blank_query_returns_no_results(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        _seed(
            client,
            token,
            workspace["id"],
            "mitochondria.txt",
            MITO_TEXT.encode(),
        )
        response = _search(client, token, workspace["id"], "   ")

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["total"] == 0


def test_search_returns_document_results(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _seed(
            client,
            token,
            workspace["id"],
            "mitochondria.txt",
            MITO_TEXT.encode(),
        )
        response = _search(client, token, workspace["id"], "mitochondria ATP")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    result = body["results"][0]
    assert result["id"] == document["id"]
    assert result["kind"] == "document"
    assert result["title"] == "mitochondria"
    assert result["subtitle"] == "TXT"
    assert result["to"] == "/library"


def test_search_ranks_more_relevant_document_first(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        _seed(client, token, workspace["id"], "photo.txt", PHOTO_TEXT.encode())
        mito = _seed(client, token, workspace["id"], "mito.txt", MITO_TEXT.encode())
        response = _search(
            client, token, workspace["id"], "NADH FADH2 proton gradient ATP"
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["id"] == mito["id"]


def test_search_returns_one_result_per_document(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _seed(
            client,
            token,
            workspace["id"],
            "long.txt",
            LONG_TEXT_MULTI_CHUNK.encode(),
        )
        response = _search(client, token, workspace["id"], "ATP")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == document["id"]


def test_search_limit_truncates_results(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        for i, text in enumerate((LONG_TEXT, MITO_TEXT, PHOTO_TEXT)):
            _seed(client, token, workspace["id"], f"doc{i}.txt", text.encode())
        response = _search(client, token, workspace["id"], "ATP", limit=2)

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2
    assert body["total"] == 2


def test_search_kinds_filter(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        _seed(client, token, workspace["id"], "mito.txt", MITO_TEXT.encode())
        query = {"q": "ATP", "workspace_id": workspace["id"]}
        documents_only = client.get(
            "/search",
            params={**query, "kinds": "document"},
            headers=_auth(token),
        )
        questions_only = client.get(
            "/search",
            params={**query, "kinds": "question"},
            headers=_auth(token),
        )
        mixed = client.get(
            "/search",
            params=[
                ("q", "ATP"),
                ("workspace_id", workspace["id"]),
                ("kinds", "flashcard"),
                ("kinds", "document"),
            ],
            headers=_auth(token),
        )

    assert documents_only.json()["total"] == 1
    assert questions_only.json()["results"] == []
    assert questions_only.json()["total"] == 0
    assert mixed.json()["total"] == 1


def test_search_workspaces_are_isolated(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        first = _create_workspace(client, token, name="Biology")
        second = _create_workspace(client, token, name="Chemistry")
        _seed(client, token, first["id"], "mito.txt", MITO_TEXT.encode())

        in_first = _search(client, token, first["id"], "ATP")
        in_second = _search(client, token, second["id"], "ATP")

    assert in_first.json()["total"] == 1
    assert in_second.json()["results"] == []


# --------------------------------------------------------------------------- #
# Grounded context (M5 plumbing)
# --------------------------------------------------------------------------- #


def test_grounded_context_produces_citations(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        document = _seed(
            client,
            token,
            workspace["id"],
            "mitochondria.txt",
            MITO_TEXT.encode(),
        )
        context = search_service.build_grounded_context(
            query="mitochondria ATP",
            workspace_id=workspace["id"],
            top_k=5,
            chroma_dir="",
        )

    assert context.is_sufficient
    assert context.chunk_ids == [
        retrieved.chunk.chunk_id for retrieved in context.chunks
    ]
    references = context.to_content_references()
    assert len(references) == len(context.chunks)
    assert references[0].segment_id == context.chunk_ids[0]
    assert all(ref.text for ref in references)
    assert context.chunks[0].chunk.document_id == document["id"]


def test_grounded_context_empty_scope_is_not_sufficient(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        context = search_service.build_grounded_context(
            query="anything",
            workspace_id=workspace["id"],
            chroma_dir="",
        )

    assert context.is_sufficient is False
    assert context.chunks == []


def test_search_response_schema_shapes(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _token(client, STUDENT)
        workspace = _create_workspace(client, token)
        response = _search(client, token, workspace["id"], "x")

    assert isinstance(response.json(), dict)
    body = SearchResponse(**response.json())
    assert body.total == len(body.results)
