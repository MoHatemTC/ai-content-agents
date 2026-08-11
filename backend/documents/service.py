"""Service functions for the documents & upload domain (M3).

The FastAPI layer owns the workspace-scoped *records* (the ``documents`` and
``document_chunks`` tables — the ``src/`` store is single-user with no
workspace concept), but every stage of the pipeline reuses the domain logic in
``src/`` rather than reimplementing it:

* extraction — :class:`src.ingestion.parser.TextParser` (txt/pdf/docx/markdown),
* normalisation — :class:`src.ingestion.cleaner.TextCleaner`,
* quality gate — :class:`src.ingestion.quality.QualityChecker`,
* chunking — :class:`src.ingestion.chunker.TextChunker` (the same boundaries
  and ``{document_id}-c{ordinal:04d}`` ids the retrieval lane uses),
* embedding — :class:`src.retrieval.index.ChunkIndex` via
  :func:`src.validation.integration.to_retrieval_chunks`, one Chroma
  collection per workspace (``workspace_<id>``).

The one adapter extension is per-page PDF extraction: the domain parser
returns concatenated text only, and ``WsChunk.page`` needs a real page number,
so this module reads PyMuPDF page-by-page (same library the parser uses) and
records the cleaned-text offsets each page starts at.

Status values stored on the row use the ``docs/DATABASE_SCHEMA.md`` enum
(``uploaded|parsing|embedding|indexed|failed``); the API-level ``WsDoc.status``
is the frontend's ``Ready|Processing`` pair — ``indexed``/``uploaded`` read as
``Ready``, everything else as ``Processing``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from src.ingestion.chunker import TextChunker
from src.ingestion.cleaner import TextCleaner
from src.ingestion.parser import TextParser
from src.ingestion.quality import QualityChecker
from src.ingestion.schema import Chunk as IngestionChunk
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex
from src.validation.integration import to_retrieval_chunks

from .schemas import (
    ChunkDocumentResponse,
    EmbedDocumentResponse,
    GetChunksResponse,
    GetDocumentsResponse,
    ParseDocumentResponse,
    UploadDocumentResponse,
    WsChunk,
    WsDoc,
)

_SUPPORTED_KINDS = {"pdf": "PDF", "docx": "DOCX", "txt": "TXT", "md": "TXT"}
_UNSUPPORTED = {"ppt", "pptx", "note"}

DB_UPLOADED = "uploaded"
DB_PARSING = "parsing"
DB_EMBEDDING = "embedding"
DB_INDEXED = "indexed"
DB_FAILED = "failed"

_READY_STATUSES = {DB_UPLOADED, DB_INDEXED}

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def kind_for_name(filename: str) -> str:
    """Return the API ``DocKind`` for a filename, or ``""`` when unsupported."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _SUPPORTED_KINDS:
        return _SUPPORTED_KINDS[ext]
    return ""


def human_size(size_bytes: int | None) -> str:
    """Format a byte count the way the frontend does (``"4.2 MB"`` / ``"123 KB"``)."""
    if not size_bytes:
        return ""
    if size_bytes < 1024 * 1024:
        return f"{max(1, round(size_bytes / 1024))} KB"
    return f"{(size_bytes / (1024 * 1024)):.1f} MB"


def token_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _db_status_to_api(status: str) -> str:
    return "Ready" if status in _READY_STATUSES else "Processing"


# --------------------------------------------------------------------------- #
# Row → schema mappers
# --------------------------------------------------------------------------- #


def row_to_doc(row: sqlite3.Row) -> WsDoc:
    return WsDoc(
        id=row["id"],
        title=row["title"],
        kind=row["kind"],
        size=row["size_human"],
        pages=row["pages"],
        uploaded=(row["created_at"] or "")[:10],
        status=_db_status_to_api(row["status"]),
        tags=json.loads(row["tags_json"] or "[]"),
        notes=row["notes"],
        chunks=[],
        storagePath=row["storage_path"],
        sizeBytes=row["size_bytes"],
    )


def row_to_chunk(row: sqlite3.Row) -> WsChunk:
    return WsChunk(
        id=row["id"],
        page=row["page"],
        tokens=row["token_count"],
        text=row["text"],
        tags=json.loads(row["tags_json"] or "[]"),
        section=row["section"],
    )


# --------------------------------------------------------------------------- #
# Extraction / parse
# --------------------------------------------------------------------------- #


def _extract_pdf_pages(file_bytes: bytes) -> list[str]:
    """Return per-page raw text for a PDF.

    Adapter extension over ``TextParser.parse_pdf`` (which returns concatenated
    text): the same PyMuPDF reader, page by page, so ``WsChunk.page`` can carry
    a real page number.
    """
    import fitz

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


def parse_text_and_pages(
    file_bytes: bytes, kind: str, filename: str = ""
) -> tuple[str, int | None, list[dict[str, int]]]:
    """Extract, clean and quality-check a file's bytes.

    Returns ``(cleaned_text, page_count, page_offsets)`` where ``page_offsets``
    maps cleaned-text character starts to 1-based page numbers (PDFs only).
    Raises ``ValueError`` when the content fails the quality gate.
    """
    raw_pages: list[str] | None = None
    if kind == "PDF":
        raw_pages = _extract_pdf_pages(file_bytes)
        cleaned_pages = [TextCleaner.clean(page) for page in raw_pages]
        page_offsets: list[dict[str, int]] = []
        cursor = 0
        for page_number, cleaned in enumerate(cleaned_pages, start=1):
            page_offsets.append({"start": cursor, "page": page_number})
            cursor += len(cleaned) + 1
        cleaned = " ".join(cleaned_pages)
        page_count: int | None = len(raw_pages)
    else:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "md":
            whole = TextParser.parse_markdown(file_bytes)
        elif kind == "DOCX":
            whole = TextParser.parse_docx(file_bytes)
        else:
            whole = TextParser.parse_txt(file_bytes)
        cleaned = TextCleaner.clean(whole)
        page_count = None
        page_offsets = []

    result = QualityChecker().validate(cleaned)
    if not result.passed:
        raise ValueError(
            " | ".join(result.issues) or "Document did not pass quality checks"
        )
    return cleaned, page_count, page_offsets


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def create_document(
    conn: sqlite3.Connection,
    owner_id: str,
    workspace_id: str,
    filename: str,
    file_bytes: bytes,
) -> UploadDocumentResponse:
    document_id = str(uuid.uuid4())
    title = filename.rsplit(".", 1)[0]
    storage_path = f"{workspace_id}/{document_id}/{filename}"
    created_at = now().isoformat()
    conn.execute(
        """
        INSERT INTO documents (
            id, workspace_id, uploaded_by, title, kind, size_bytes, size_human,
            pages, status, tags_json, notes, storage_path, file_bytes, text,
            text_length, chunk_count, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            workspace_id,
            owner_id,
            title,
            kind_for_name(filename),
            len(file_bytes),
            human_size(len(file_bytes)),
            None,
            DB_UPLOADED,
            "[]",
            None,
            storage_path,
            file_bytes,
            None,
            0,
            0,
            created_at,
            created_at,
        ),
    )
    conn.commit()
    row = get_document_row(conn, document_id)
    assert row is not None
    return UploadDocumentResponse(document=row_to_doc(row), storage_path=storage_path)


def get_document_row(conn: sqlite3.Connection, document_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()


def get_owned_document_row(
    conn: sqlite3.Connection, owner_id: str, document_id: str
) -> sqlite3.Row | None:
    """A document whose workspace is owned by ``owner_id``, or ``None``."""
    return conn.execute(
        """
        SELECT d.* FROM documents d
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE d.id = ? AND w.owner_id = ?
        """,
        (document_id, owner_id),
    ).fetchone()


def list_documents(conn: sqlite3.Connection, workspace_id: str) -> GetDocumentsResponse:
    rows = conn.execute(
        "SELECT * FROM documents WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    ).fetchall()
    return GetDocumentsResponse(documents=[row_to_doc(row) for row in rows])


def list_chunks(conn: sqlite3.Connection, document_id: str) -> GetChunksResponse:
    rows = conn.execute(
        "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY ordinal",
        (document_id,),
    ).fetchall()
    return GetChunksResponse(chunks=[row_to_chunk(row) for row in rows])


# --------------------------------------------------------------------------- #
# Pipeline stages
# --------------------------------------------------------------------------- #


def _set_status(conn: sqlite3.Connection, document_id: str, status: str) -> None:
    conn.execute(
        "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
        (status, now().isoformat(), document_id),
    )


def parse_document(
    conn: sqlite3.Connection, document_id: str, row: sqlite3.Row | None = None
) -> ParseDocumentResponse:
    row = row or get_document_row(conn, document_id)
    if row is None:
        raise LookupError("document")
    if not row["file_bytes"]:
        raise LookupError("file_bytes")
    _set_status(conn, document_id, DB_PARSING)
    try:
        cleaned, page_count, page_offsets = parse_text_and_pages(
            row["file_bytes"], row["kind"], filename=row["storage_path"] or ""
        )
    except ValueError as exc:
        _set_status(conn, document_id, DB_FAILED)
        conn.commit()
        raise ValueError(str(exc)) from exc
    conn.execute(
        """
        UPDATE documents
        SET text = ?, text_length = ?, pages = ?, page_offsets_json = ?, status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            cleaned,
            len(cleaned),
            page_count,
            json.dumps(page_offsets),
            DB_PARSING,
            now().isoformat(),
            document_id,
        ),
    )
    conn.commit()
    return ParseDocumentResponse(
        documentId=document_id, pages=page_count, text_length=len(cleaned)
    )


def _page_for_offset(page_offsets: list[dict[str, int]], start_char: int) -> int | None:
    page: int | None = None
    for offset in page_offsets:
        if offset["start"] <= start_char:
            page = offset["page"]
        else:
            break
    return page


def chunk_document(
    conn: sqlite3.Connection, document_id: str, row: sqlite3.Row | None = None
) -> ChunkDocumentResponse:
    row = row or get_document_row(conn, document_id)
    if row is None:
        raise LookupError("document")
    if not row["text"]:
        raise LookupError("text")
    config = RetrievalConfig()
    chunker = TextChunker(chunk_size=config.chunk_size, overlap=config.chunk_overlap)
    ingestion_chunks = chunker.chunk(row["text"], document_id)
    page_offsets = json.loads(row["page_offsets_json"] or "[]")

    conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    created_at = now().isoformat()
    for chunk in ingestion_chunks:
        conn.execute(
            """
            INSERT INTO document_chunks (
                id, document_id, workspace_id, ordinal, page, token_count, text,
                tags_json, section, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.id,
                document_id,
                row["workspace_id"],
                chunk.ordinal,
                _page_for_offset(page_offsets, chunk.start_char or 0),
                token_count(chunk.text),
                chunk.text,
                "[]",
                None,
                created_at,
            ),
        )
    conn.execute(
        """
        UPDATE documents SET chunk_count = ?, status = ?, updated_at = ? WHERE id = ?
        """,
        (len(ingestion_chunks), DB_PARSING, now().isoformat(), document_id),
    )
    conn.commit()
    chunks = [
        WsChunk(
            id=chunk.id,
            page=_page_for_offset(page_offsets, chunk.start_char or 0),
            tokens=token_count(chunk.text),
            text=chunk.text,
            tags=[],
            section=None,
        )
        for chunk in ingestion_chunks
    ]
    return ChunkDocumentResponse(documentId=document_id, chunks=chunks)


def embed_document(
    conn: sqlite3.Connection,
    document_id: str,
    workspace_id: str,
    chroma_dir: str | None,
    row: sqlite3.Row | None = None,
) -> EmbedDocumentResponse:
    row = row or get_document_row(conn, document_id)
    if row is None:
        raise LookupError("document")
    rows = conn.execute(
        "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY ordinal",
        (document_id,),
    ).fetchall()
    if not rows:
        raise LookupError("chunks")
    ingestion_chunks = [
        IngestionChunk(
            id=chunk_row["id"],
            document_id=document_id,
            text=chunk_row["text"],
            ordinal=chunk_row["ordinal"],
        )
        for chunk_row in rows
    ]
    retrieval_chunks = to_retrieval_chunks(ingestion_chunks)
    _set_status(conn, document_id, DB_EMBEDDING)
    conn.commit()
    try:
        index = ChunkIndex(
            RetrievalConfig(
                collection_name=f"workspace_{workspace_id}",
                persist_directory=chroma_dir or None,
            )
        )
        embedded = index.add_document(document_id, retrieval_chunks)
    except Exception:
        _set_status(conn, document_id, DB_FAILED)
        conn.commit()
        raise
    model = os.getenv("RETRIEVAL_EMBEDDER", "onnx")
    _set_status(conn, document_id, DB_INDEXED)
    conn.commit()
    return EmbedDocumentResponse(documentId=document_id, embedded=embedded, model=model)


def save_notes(conn: sqlite3.Connection, document_id: str, notes: str) -> None:
    conn.execute(
        "UPDATE documents SET notes = ?, updated_at = ? WHERE id = ?",
        (notes, now().isoformat(), document_id),
    )
    conn.commit()


def update_document(
    conn: sqlite3.Connection,
    document_id: str,
    *,
    title: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
    pages: int | None = None,
    size_bytes: int | None = None,
) -> None:
    """Persist editable fields (title, notes, topics, pages, size) on a document."""
    sets: list[str] = []
    values: list[object] = []
    if title is not None:
        sets.append("title = ?")
        values.append(title)
    if notes is not None:
        sets.append("notes = ?")
        values.append(notes)
    if tags is not None:
        sets.append("tags_json = ?")
        values.append(json.dumps(tags))
    if pages is not None:
        sets.append("pages = ?")
        values.append(pages)
    if size_bytes is not None:
        sets.append("size_bytes = ?")
        values.append(size_bytes)
    if not sets:
        return
    sets.append("updated_at = ?")
    values.append(now().isoformat())
    values.append(document_id)
    conn.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = ?", values)
    conn.commit()


def delete_document(
    conn: sqlite3.Connection,
    document_id: str,
    workspace_id: str,
    chroma_dir: str | None,
) -> None:
    # Best-effort index cleanup: a stale collection must never block deleting
    # the record (e.g. the embedder changed and Chroma now refuses to open it).
    try:
        index = ChunkIndex(
            RetrievalConfig(
                collection_name=f"workspace_{workspace_id}",
                persist_directory=chroma_dir or None,
            )
        )
        index.remove_document(document_id)
    except Exception:  # noqa: BLE001 - cleanup failure must not block deletion
        logger.warning(
            "could not purge retrieval index for document %s (workspace %s)",
            document_id,
            workspace_id,
        )
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()


def workspace_document_count(conn: sqlite3.Connection, workspace_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM documents WHERE workspace_id = ?", (workspace_id,)
    ).fetchone()
    return int(row["c"])
