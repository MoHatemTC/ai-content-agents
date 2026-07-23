
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Document(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the document")
    title: str = Field(..., description="Title of the document")
    content: str = Field(..., description="Cleaned text content of the document")
    source_type: str = Field(..., description="Source type (e.g., 'file', 'paste')")
    file_type: Optional[str] = Field(None, description="File type (e.g., 'txt', 'pdf', 'docx', 'md')")
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="Timestamp when document was created")
    content_hash: Optional[str] = Field(None, description="Hash of the content for deduplication")


class Chunk(BaseModel):
    id: str = Field(..., description="Unique stable identifier for the chunk, formatted as {document_id}-c{ordinal:04d}")
    document_id: str = Field(..., description="ID of the parent document")
    text: str = Field(..., description="Text content of the chunk")
    ordinal: int = Field(..., description="0-based index of the chunk within the document")
    start_char: Optional[int] = Field(None, description="Start character position in original document")
    end_char: Optional[int] = Field(None, description="End character position in original document")
    session_id: Optional[str] = Field(None, description="Optional session ID for session-scoped retrieval")
