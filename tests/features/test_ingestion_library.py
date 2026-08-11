"""
Tests for the content library service.

These tests verify that the content library correctly lists, retrieves,
and deletes ingested documents while maintaining accurate metadata.
"""

from __future__ import annotations

import os
import tempfile

from src.ingestion.library import ContentLibrary
from src.ingestion.loader import ContentLoader


def test_list_documents():
    """
    Verify that uploaded documents appear in the content library.

    The test uploads a document through the content loader, retrieves the
    document list from the library, and confirms that the uploaded document
    is present with the expected title.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        library = ContentLibrary(db_path)

        loader.load_text(
            "This is a sufficiently long document for testing the library. " * 3,
            title="Test Document",
        )

        documents = library.list_documents()

        assert len(documents) == 1
        assert documents[0].title == "Test Document"

    finally:
        os.unlink(db_path)


def test_delete_document():
    """
    Verify that deleting a document removes it from the library.

    The test uploads a document, confirms that it exists, deletes it,
    and verifies that the document can no longer be found.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        library = ContentLibrary(db_path)

        doc = loader.load_text(
            "This is a sufficiently long document for deletion testing. " * 3,
            title="Delete Me",
        )

        assert library.document_exists(doc.id)

        deleted = library.delete_document(doc.id)

        assert deleted
        assert not library.document_exists(doc.id)
        assert library.list_documents() == []

    finally:
        os.unlink(db_path)


def test_get_document():
    """
    Verify that a document can be retrieved by its identifier.

    The test uploads a document, retrieves it using its unique identifier,
    and confirms that the returned document matches the stored one.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        library = ContentLibrary(db_path)

        doc = loader.load_text(
            "This document will be retrieved later. " * 5,
            title="Retrieve",
        )

        retrieved = library.get_document(doc.id)

        assert retrieved is not None
        assert retrieved.id == doc.id
        assert retrieved.title == "Retrieve"

    finally:
        os.unlink(db_path)
