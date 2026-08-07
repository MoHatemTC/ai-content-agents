"""Request/response schemas for the documents & upload endpoints (M3).

Shapes match Sensei-AI ``src/types/api/document.contracts.ts`` and
``src/types/domain.ts`` (``WsDoc`` / ``WsChunk``) and the example payloads in
``docs/FASTAPI_INTEGRATION.md``: ``POST /upload`` returns
``{ document, storage_path }``; parse/chunk/embed return
``{ documentId, ... }``; chunks list is ``{ chunks }``; notes is a 204 PATCH.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocKind = Literal["PDF", "DOCX", "PPTX", "TXT", "Note"]
DocStatus = Literal["Ready", "Processing"]


class WsChunk(BaseModel):
    id: str
    page: int | None = None
    tokens: int = 0
    text: str
    tags: list[str] = Field(default_factory=list)
    section: str | None = None


class WsDoc(BaseModel):
    id: str
    title: str
    kind: DocKind
    size: str
    pages: int | None = None
    uploaded: str
    status: DocStatus = "Ready"
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    chunks: list[WsChunk] = Field(default_factory=list)
    storagePath: str | None = None
    sizeBytes: int | None = None


class UploadDocumentResponse(BaseModel):
    document: WsDoc
    storage_path: str


class ParseDocumentResponse(BaseModel):
    documentId: str
    pages: int | None
    text_length: int


class ChunkDocumentResponse(BaseModel):
    documentId: str
    chunks: list[WsChunk]


class EmbedDocumentResponse(BaseModel):
    documentId: str
    embedded: int
    model: str


class GetDocumentsResponse(BaseModel):
    documents: list[WsDoc]


class GetChunksResponse(BaseModel):
    chunks: list[WsChunk]


class SaveDocumentNotesRequest(BaseModel):
    notes: str


class PatchDocumentRequest(BaseModel):
    """Editable document fields (title, notes, tags, pages, size)."""

    title: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    pages: int | None = None
    sizeBytes: int | None = None
