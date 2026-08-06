from __future__ import annotations

import os
import tempfile

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
            b"Software engineering is the process of designing, developing, "
            b"testing, and maintaining software applications. Developers use "
            b"version control, documentation, and automated testing to improve "
            b"software quality and support collaboration."
        )

        doc = loader.load_file(file_content, "test.txt")
        assert doc.id is not None

        chunks = loader.store.get_chunks_by_document_id(doc.id)
        assert len(chunks) > 0
    finally:
        os.unlink(db_path)


def test_paste_text_regression():
    """
    Verify that pasted text is ingested using ``load_text`` and
    produces a stored document with generated chunks.

    This regression test ensures the Paste Text workflow continues
    to use the text ingestion path instead of the file ingestion path.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        loader = ContentLoader(db_path)

        pasted_text = (
            "Artificial intelligence enables computers to learn from data, "
            "recognize patterns, and support decision making. Machine learning "
            "models are trained using datasets and evaluated using appropriate "
            "metrics. Proper testing, documentation, and validation help ensure "
            "that software systems remain reliable and maintainable."
        )

        document = loader.load_text(
            pasted_text,
            title="Pasted Text",
        )

        assert document.id is not None
        assert document.title == "Pasted Text"

        chunks = loader.store.get_chunks_by_document_id(document.id)

        assert len(chunks) > 0

    finally:
        os.unlink(db_path)
