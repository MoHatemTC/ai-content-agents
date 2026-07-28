
from __future__ import annotations

import tempfile
import os
from src.ingestion.loader import ContentLoader


def test_load_text():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)
        text = (
               "Artificial intelligence enables computers to learn from data, "
               "recognize patterns, and support decision making. Machine learning "
               "models are trained using datasets and evaluated using appropriate "
               "metrics. Proper testing, documentation, and validation help ensure "
               "that software systems remain reliable and maintainable."
        )

        doc = loader.load_text(text, title="Test Load")
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
        file_content = (
                        "Software engineering is the process of designing, developing, "
                        "testing, and maintaining software applications. Developers use "
                        "version control, documentation, and automated testing to improve "
                        "software quality and support collaboration."
        ).encode("utf-8")

        doc = loader.load_file(file_content, "test.txt")
        assert doc.id is not None

        chunks = loader.store.get_chunks_by_document_id(doc.id)
        assert len(chunks) > 0
    finally:
        os.unlink(db_path)
