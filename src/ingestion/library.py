"""
High-level content library service.

This module provides a clean interface for browsing and managing
ingested documents without exposing the underlying SQLite storage
implementation.
"""

from __future__ import annotations

from .schema import Document, DocumentMetadata
from .store import SQLiteStore


class ContentLibrary:
    """
    High-level service for accessing the document library.

    This class wraps the SQLite storage layer and exposes
    document metadata suitable for user interfaces and
    downstream components.
    """

    def __init__(self, db_path: str = "ingestion.db") -> None:
        """
        Initialize the content library.

        Args:
            db_path:
                Path to the SQLite database.
        """
        self.store = SQLiteStore(db_path)

    def _build_metadata(self, document: Document) -> DocumentMetadata:
        """
        Build metadata for a document.

        Args:
            document:
                The document to summarize.

        Returns:
            A DocumentMetadata instance containing information
            about the document.
        """
        return DocumentMetadata(
            id=document.id,
            title=document.title,
            source_type=document.source_type,
            file_type=document.file_type,
            size=len(document.content),
            chunk_count=self.store.count_chunks(document.id),
            created_at=document.created_at,
        )

    def list_documents(self) -> list[DocumentMetadata]:
        """
        Retrieve metadata for every stored document.

        Returns:
            A list of document metadata ordered by creation date.
        """
        documents = self.store.get_all_documents()

        return [self._build_metadata(document) for document in documents]

    def get_document(self, document_id: str) -> Document | None:
        """
        Retrieve a document by its identifier.

        Args:
            document_id:
                The document identifier.

        Returns:
            The matching document if found; otherwise None.
        """
        return self.store.get_document_by_id(document_id)

    def get_document_metadata(self, document_id: str) -> DocumentMetadata | None:
        """
        Retrieve metadata for a single document.

        Args:
            document_id:
                The document identifier.

        Returns:
            The document metadata if found; otherwise None.
        """
        document = self.store.get_document_by_id(document_id)

        if document is None:
            return None

        return self._build_metadata(document)

    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document and its associated chunks.

        Args:
            document_id:
                Identifier of the document to delete.

        Returns:
            True if the document was deleted;
            otherwise False.
        """
        return self.store.delete_document(document_id)

    def document_exists(self, document_id: str) -> bool:
        """
        Determine whether a document exists.

        Args:
            document_id:
                The document identifier.

        Returns:
            True if the document exists; otherwise False.
        """
        return self.store.document_exists(document_id)
