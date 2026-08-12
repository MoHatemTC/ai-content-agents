"""Service functions for the M4 retrieval/search domain.

The read model is workspace-scoped (one Chroma collection per workspace,
``workspace_<id>``, built and kept in sync by the M3 pipeline), and every
query reuses the domain retrieval components in ``src/retrieval`` rather than
reimplementing them:

* :class:`src.retrieval.index.ChunkIndex` — open/reopen the workspace index,
* :class:`src.retrieval.retriever.ChromaRetriever` — top-k cosine ranking with
  the ``min_score`` floor and deterministic tie-breaks,
* :class:`src.retrieval.config.RetrievalConfig` — tunables (``top_k``,
  ``persist_directory``, ``collection_name``),
* :class:`src.retrieval.models.RetrievalScope` — the scope is ``workspace_id``
  only (the M4 extension): the collection *is* the workspace, so Chroma is
  queried with no metadata filter,
* :class:`src.retrieval.models.GroundedContext` — the grounded-context payload
  (``as_prompt_content`` / ``to_content_references`` / ``chunk_ids``) that M5
  generation consumes for grounding scores, citations and provenance.

Only ``document``-kind results exist in M4; the other ``SearchResultKind``
values depend on their owning milestones and simply produce empty results.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex
from src.retrieval.models import GroundedContext, RetrievalScope
from src.retrieval.retriever import ChromaRetriever
from src.retrieval.structure import (
    STRUCTURE_BACK_MATTER,
    STRUCTURE_FRONT_MATTER,
    ordinal_range_for,
    parse_structure_ref,
)

from .schemas import SUPPORTED_SEARCH_KIND, SearchResponse, SearchResult

DEFAULT_SEARCH_LIMIT = 40


def _workspace_index(
    workspace_id: str, chroma_dir: str | None, top_k: int
) -> ChunkIndex:
    """Open the workspace's retrieval index with the M3 collection scheme."""
    config = RetrievalConfig(
        collection_name=f"workspace_{workspace_id}",
        persist_directory=chroma_dir or None,
        top_k=top_k,
    )
    return ChunkIndex(config)


def _to_response(
    conn: sqlite3.Connection,
    workspace_id: str,
    retrieved: list,
) -> SearchResponse:
    """Map retrieved chunks to contract-shaped results, one per document.

    Results are grouped by document (best chunk score wins), hydrated with the
    persisted title/kind/pages metadata, ordered by best score with a
    deterministic tie-break, and limited to the already-retrieved set.
    """
    if not retrieved:
        return SearchResponse()

    best_score: dict[str, float] = {}
    order: list[str] = []
    for hit in retrieved:
        doc_id = hit.chunk.document_id
        if doc_id not in best_score:
            best_score[doc_id] = hit.score
            order.append(doc_id)
        else:
            best_score[doc_id] = max(best_score[doc_id], hit.score)

    placeholders = ",".join("?" for _ in order)
    rows = conn.execute(
        "SELECT id, title, kind, pages FROM documents "
        f"WHERE workspace_id = ? AND id IN ({placeholders})",
        (workspace_id, *order),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}

    results: list[SearchResult] = []
    for doc_id in order:
        row = by_id.get(doc_id)
        title = row["title"] if row else doc_id
        kind = row["kind"] if row else "TXT"
        pages = row["pages"] if row else None
        subtitle = f"{kind} · {pages} pages" if pages else kind
        results.append(
            SearchResult(
                id=doc_id,
                kind=SUPPORTED_SEARCH_KIND,
                title=title,
                subtitle=subtitle,
                to="/library",
            )
        )

    results.sort(key=lambda result: (-best_score[result.id], result.id))
    return SearchResponse(results=results, total=len(results))


def search_workspace(
    conn: sqlite3.Connection,
    workspace_id: str,
    q: str,
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
    kinds: list[str] | None = None,
    chroma_dir: str | None = None,
) -> SearchResponse:
    """Search one workspace's indexed content, returning document results.

    Blank queries yield no results (the retriever short-circuits them). When
    the ``kinds`` filter excludes documents, nothing is retrieved at all — the
    other kinds do not exist yet in the backend.
    """
    if kinds and SUPPORTED_SEARCH_KIND not in kinds:
        return SearchResponse()

    index = _workspace_index(workspace_id, chroma_dir, max(limit, 1))
    retriever = ChromaRetriever(index)
    scope = RetrievalScope(workspace_id=workspace_id)
    retrieved = retriever.retrieve(q, scope, top_k=limit)
    return _to_response(conn, workspace_id, retrieved)


def _structural_range(
    query: str, document_id: str | None, db_path: str | None
) -> tuple[int, int] | None:
    """Confine retrieval to the part of a document a query is really about.

    Two cases, one mechanism. A query naming a chapter or section gets that
    chapter's ordinals. Any other query gets the document's *body* — front
    matter (title page, table of contents, preface) and back matter (the
    answer key) removed. Both are dense with section numbers and empty of
    explanation, which is why "explain chapter 4" used to come back describing
    the preface and the answers to odd-numbered exercises.

    Args:
        query: The user's question.
        document_id: The document being searched, when scoped to one.
        db_path: Where ``document_chunks`` lives. ``None`` disables routing.

    Returns:
        An inclusive ordinal span, or ``None`` to retrieve unconfined —
        which is what happens for an unlabelled document, an unmatched
        reference, or a workspace-wide search.
    """
    if not document_id or not db_path:
        return None

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ordinal, section FROM document_chunks "
            "WHERE document_id = ? ORDER BY ordinal",
            (document_id,),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    labels: list[str | None] = [row[1] for row in rows]
    if not labels or all(label is None for label in labels):
        # Unlabelled: either chunked before labelling existed, or a document
        # with no headings to find. Make no claim about its structure.
        return None

    ref = parse_structure_ref(query)
    if ref is not None:
        return ordinal_range_for(labels, ref)

    body = [
        i
        for i, label in enumerate(labels)
        if label not in (None, STRUCTURE_FRONT_MATTER, STRUCTURE_BACK_MATTER)
    ]
    if not body:
        return None
    # A body that is a minority of the document means the labelling misread
    # it. Narrowing on that would hide real material, so leave it alone.
    if len(body) * 2 < len(labels):
        return None
    return body[0], body[-1]


def build_grounded_context(
    *,
    query: str,
    workspace_id: str,
    top_k: int = 5,
    chroma_dir: str | None = None,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    session_id: str | None = None,
    db_path: str | None = None,
) -> GroundedContext:
    """Retrieve a grounded context for generation (M5 plumbing).

    Returns a :class:`GroundedContext` exposing the same contract M5 will
    consume: ``as_prompt_content`` fills a prompt's ``{content}`` slot,
    ``to_content_references`` produces ``ContentReference`` citations, and
    ``chunk_ids`` records provenance for review.
    """
    index = _workspace_index(workspace_id, chroma_dir, max(top_k, 1))
    retriever = ChromaRetriever(index)
    target_doc_id = document_id or (document_ids[0] if document_ids else None)
    scope = RetrievalScope(
        document_id=target_doc_id,
        session_id=session_id,
        workspace_id=workspace_id,
        ordinal_range=_structural_range(
            query, target_doc_id, db_path=db_path
        ),
    )
    chunks = retriever.retrieve(query, scope, top_k=top_k)
    if not chunks and len(index) > 0:
        where = scope.to_where()
        get_kwargs: dict[str, Any] = {"limit": top_k, "include": ["documents", "metadatas"]}
        if where:
            get_kwargs["where"] = where
        raw = index._collection.get(**get_kwargs)
        if raw and raw.get("ids"):
            from src.retrieval.models import Chunk, RetrievedChunk
            fallback_chunks = []
            ids = raw["ids"]
            docs = raw.get("documents") or []
            metas = raw.get("metadatas") or []
            for position, (chunk_id, text, metadata) in enumerate(
                zip(ids, docs, metas), start=1
            ):
                meta_dict = metadata if isinstance(metadata, dict) else {}
                doc_id = str(meta_dict.get("document_id") or target_doc_id or "doc-001")
                sess_id = str(meta_dict["session_id"]) if meta_dict.get("session_id") else None
                ord_val = int(meta_dict.get("ordinal", position - 1))
                c = Chunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    session_id=sess_id,
                    ordinal=max(0, ord_val),
                    text=text,
                )
                fallback_chunks.append(RetrievedChunk(chunk=c, score=0.5, rank=position))
            chunks = fallback_chunks
    return GroundedContext(query=query, scope=scope, chunks=chunks)
