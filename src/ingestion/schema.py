
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A processed document stored for downstream retrieval/agent lanes."""

    id: str | None = Field(
        None,
        description="Unique identifier for the document.",
    )
    title: str = Field(
        ...,
        description="Title of the document.",
    )
    content: str = Field(
        ...,
        description="Cleaned text content of the document.",
    )
    source_type: str = Field(
        ...,
        description="Source type (e.g. 'file', 'paste').",
    )
    file_type: str | None = Field(
        None,
        description="File type (e.g. 'txt', 'pdf', 'docx', 'md').",
    )
    created_at: datetime | None = Field(
        default_factory=datetime.now,
        description="Timestamp when document was created.",
    )
    content_hash: str | None = Field(
        None,
        description="Hash of the content for deduplication.",
    )


class Chunk(BaseModel):
    """A stable, retrieval-ready chunk belonging to a Document."""

    id: str = Field(
        ...,
        description="Unique stable identifier formatted as {document_id}-c{ordinal:04d}.",
    )
    document_id: str = Field(
        ...,
        description="ID of the parent document.",
    )
    text: str = Field(
        ...,
        description="Text content of the chunk.",
    )
    ordinal: int = Field(
        ...,
        description="0-based index of the chunk within the document.",
    )
    start_char: int | None = Field(
        None,
        description="Start character position in original document.",
    )
    end_char: int | None = Field(
        None,
        description="End character position in original document.",
    )
    session_id: str | None = Field(
        None,
        description="Optional session ID for session-scoped retrieval.",
    )
