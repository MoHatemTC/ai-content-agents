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


class DocumentMetadata(BaseModel):
    """
    Represents document metadata displayed in the content library.

    Attributes:
        id:
            Unique document identifier.
        title:
            Document title.
        source_type:
            Source of the document.
        file_type:
            Document file extension.
        size:
            Size of the document in characters.
        chunk_count:
            Number of chunks generated for the document.
        created_at:
            Timestamp when the document was ingested.
    """

    id: str = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    source_type: str = Field(..., description="Source of the document")
    file_type: str | None = Field(None, description="Document file extension")
    size: int = Field(..., description="Document size measured in characters")
    chunk_count: int = Field(
        ..., description="Number of chunks generated from the document"
    )
    created_at: datetime = Field(
        ..., description="Timestamp when the document was ingested"
    )


class FailedFile(BaseModel):
    """
    Represents a file that could not be ingested during a batch operation.

    Attributes:
        filename:
            Name of the file that failed.
        error:
            Description of the reason the file could not be processed.
    """

    filename: str = Field(..., description="Name of the failed file")
    error: str = Field(..., description="Reason why ingestion failed")


class BatchResult(BaseModel):
    """
    Represents the outcome of a batch ingestion operation.

    Attributes:
        documents:
            Successfully ingested documents.
        failed_files:
            Files that could not be processed.
    """

    documents: list[Document] = Field(
        default_factory=list, description="Successfully ingested documents"
    )

    failed_files: list[FailedFile] = Field(
        default_factory=list, description="Files that failed during batch ingestion"
    )
