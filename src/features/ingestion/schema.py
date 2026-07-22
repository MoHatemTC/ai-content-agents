
from pydantic import BaseModel, Field
from typing import List, Optional
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
    id: Optional[str] = Field(None, description="Unique identifier for the chunk")
    document_id: str = Field(..., description="ID of the parent document")
    content: str = Field(..., description="Text content of the chunk")
    chunk_index: int = Field(..., description="Index of the chunk within the document")
    start_char: Optional[int] = Field(None, description="Start character position in original document")
    end_char: Optional[int] = Field(None, description="End character position in original document")
