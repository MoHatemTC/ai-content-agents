
from __future__ import annotations

import tempfile
import os
from src.ingestion.loader import ContentLoader


def test_load_text():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        doc = loader.load_text("This is test text for loading.", title="Test Load")
        assert doc.id is not None

        chunks = loader.store.get_chunks_by_document_id(doc.id)
        assert len(chunks) > 0
    finally:
        os.unlink(db_path)


def test_load_file():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        file_content = b"This is a test text file content."
        doc = loader.load_file(file_content, "test.txt")
        assert doc.id is not None

        chunks = loader.store.get_chunks_by_document_id(doc.id)
        assert len(chunks) > 0
    finally:
        os.unlink(db_path)
