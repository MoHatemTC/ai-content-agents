"""Documents & upload API routes (M3).

Implements the pipeline the frontend drives against
``docs/FASTAPI_INTEGRATION.md`` and ``Sensei-AI/docs/BACKEND_CONTRACT.md``:

* ``POST /upload`` (multipart ``workspace_id`` + ``file``) → document record +
  storage path,
* ``POST /documents/{id}/parse`` / ``/chunk`` / ``/embed`` → pipeline stages,
* ``GET /documents?workspace_id=`` → workspace document list,
* ``GET /documents/{id}/chunks`` → stored chunks,
* ``PATCH /documents/{id}/notes`` → lecture notes,
* ``DELETE /documents/{id}`` → record, chunks and index rows.

Every route is scoped to the caller: a document is only visible when its
workspace belongs to the authenticated user (403 otherwise, 404 when the
document does not exist).
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from backend.auth.schemas import AuthUser
from backend.deps import get_current_user, get_db
from backend.errors import ApiError
from backend.workspaces import service as workspaces_service

from . import service
from .schemas import (
    ChunkDocumentResponse,
    EmbedDocumentResponse,
    GetChunksResponse,
    GetDocumentsResponse,
    ParseDocumentResponse,
    PatchDocumentRequest,
    SaveDocumentNotesRequest,
    UploadDocumentResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])
upload_router = APIRouter(tags=["documents"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]
User = Annotated[AuthUser, Depends(get_current_user)]

_STAGE_ERRORS = {
    "document": ApiError(
        status_code=404, code="not_found", message="Document not found"
    ),
    "file_bytes": ApiError(
        status_code=422,
        code="validation_error",
        message="Document has no stored file to parse",
    ),
    "text": ApiError(
        status_code=409,
        code="conflict",
        message="Document has not been parsed yet",
    ),
    "chunks": ApiError(
        status_code=409,
        code="conflict",
        message="Document has not been chunked yet",
    ),
}


def _get_owned_document(db: sqlite3.Connection, user: AuthUser, document_id: str):
    """Return the caller's document row, raising the contract's 403/404 errors."""
    row = service.get_owned_document_row(db, user.id, document_id)
    if row is None:
        if service.get_document_row(db, document_id) is None:
            raise ApiError(
                status_code=404, code="not_found", message="Document not found"
            )
        raise ApiError(
            status_code=403,
            code="forbidden",
            message="Not allowed to access this document",
        )
    return row


def _require_workspace(
    db: sqlite3.Connection, user: AuthUser, workspace_id: str
) -> None:
    row = workspaces_service.get_workspace(db, workspace_id)
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Workspace not found")
    if row["owner_id"] != user.id:
        raise ApiError(
            status_code=403,
            code="forbidden",
            message="Not allowed to access this workspace",
        )


def _stage_error(key: str, detail: str = "") -> ApiError:
    error = _STAGE_ERRORS[key]
    return ApiError(
        status_code=error.status_code,
        code=error.code,
        message=f"{error.message}{f': {detail}' if detail else ''}",
    )


@upload_router.post("/upload", response_model=UploadDocumentResponse, status_code=201)
@router.post("/upload", response_model=UploadDocumentResponse, status_code=201)
def upload_document(
    db: Db,
    user: User,
    request: Request,
    workspace_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> UploadDocumentResponse:
    """Store an uploaded file's bytes and create its document record."""
    _require_workspace(db, user, workspace_id)
    if not service.kind_for_name(file.filename or ""):
        raise ApiError(
            status_code=422,
            code="validation_error",
            message="Unsupported file type; upload a PDF, DOCX, TXT or Markdown file",
        )
    max_bytes = request.app.state.settings.max_upload_bytes
    file_bytes = file.file.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise ApiError(
            status_code=413,
            code="payload_too_large",
            message=f"File exceeds the {max_bytes} byte upload limit",
        )
    return service.create_document(
        db, user.id, workspace_id, file.filename or "document.txt", file_bytes
    )


@router.get("", response_model=GetDocumentsResponse)
def get_documents(db: Db, user: User, workspace_id: str = "") -> GetDocumentsResponse:
    """List the documents belonging to one workspace (newest first)."""
    if not workspace_id:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message="workspace_id query parameter is required",
        )
    _require_workspace(db, user, workspace_id)
    return service.list_documents(db, workspace_id)


@router.post("/{document_id}/parse", response_model=ParseDocumentResponse)
def parse_document(document_id: str, db: Db, user: User) -> ParseDocumentResponse:
    """Extract, clean and quality-check the stored file, then persist the text."""
    row = _get_owned_document(db, user, document_id)
    try:
        return service.parse_document(db, document_id, row)
    except LookupError as exc:
        raise _stage_error(str(exc)) from exc
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message="Document did not pass quality checks",
            details={"issues": str(exc)},
        ) from exc


@router.post("/{document_id}/chunk", response_model=ChunkDocumentResponse)
def chunk_document(document_id: str, db: Db, user: User) -> ChunkDocumentResponse:
    """Split the parsed text into retrieval-stable chunks and persist them."""
    row = _get_owned_document(db, user, document_id)
    try:
        return service.chunk_document(db, document_id, row)
    except LookupError as exc:
        raise _stage_error(str(exc)) from exc


@router.post("/{document_id}/embed", response_model=EmbedDocumentResponse)
def embed_document(
    document_id: str, db: Db, user: User, request: Request
) -> EmbedDocumentResponse:
    """Embed the stored chunks into the workspace's retrieval index."""
    row = _get_owned_document(db, user, document_id)
    try:
        return service.embed_document(
            db,
            document_id,
            row["workspace_id"],
            request.app.state.settings.chroma_dir,
            row,
        )
    except LookupError as exc:
        raise _stage_error(str(exc)) from exc


@router.get("/{document_id}/chunks", response_model=GetChunksResponse)
def get_chunks(document_id: str, db: Db, user: User) -> GetChunksResponse:
    """Return the document's stored chunks in ordinal order."""
    _get_owned_document(db, user, document_id)
    return service.list_chunks(db, document_id)


@router.patch("/{document_id}/notes", status_code=204)
def save_notes(
    document_id: str, payload: SaveDocumentNotesRequest, db: Db, user: User
) -> None:
    """Persist free-text lecture notes against a document."""
    _get_owned_document(db, user, document_id)
    service.save_notes(db, document_id, payload.notes)


@router.patch("/{document_id}", status_code=204)
def patch_document(
    document_id: str, payload: PatchDocumentRequest, db: Db, user: User
) -> None:
    """Persist editable document fields (title, notes, tags, pages, size)."""
    _get_owned_document(db, user, document_id)
    service.update_document(
        db,
        document_id,
        title=payload.title,
        notes=payload.notes,
        tags=payload.tags,
        pages=payload.pages,
        size_bytes=payload.sizeBytes,
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, db: Db, user: User, request: Request) -> None:
    """Remove the document, its chunks and its retrieval index rows."""
    row = _get_owned_document(db, user, document_id)
    service.delete_document(
        db, document_id, row["workspace_id"], request.app.state.settings.chroma_dir
    )
