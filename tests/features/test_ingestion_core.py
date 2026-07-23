
from __future__ import annotations

import tempfile
import os
from src.ingestion.schema import Document, Chunk
from src.ingestion.parser import TextParser
from src.ingestion.cleaner import TextCleaner
from src.ingestion.chunker import TextChunker
from src.ingestion.dedupe import Deduplicator
from src.ingestion.store import SQLiteStore


def test_text_cleaner():
    cleaner = TextCleaner()
    text = "  Hello   world!  \n\nThis is a test.  "
    cleaned = cleaner.clean(text)
    assert cleaned == "Hello world! This is a test."


def test_text_chunker():
    chunker = TextChunker(chunk_size=10, overlap=2)
    text = "1234567890abcdefghij"
    chunks = chunker.chunk(text, "test-doc-id")
    assert len(chunks) > 0
    assert chunks[0].text == "1234567890"
    assert chunks[0].id == "test-doc-id-c0000"
    assert chunks[1].text == "90abcdefgh"


def test_deduplicator():
    content = "test content"
    hash1 = Deduplicator.compute_hash(content)
    hash2 = Deduplicator.compute_hash(content)
    assert hash1 == hash2


def test_parser_txt():
    content = b"Hello, this is a test file."
    parsed = TextParser.parse_txt(content)
    assert "Hello, this is a test file." in parsed


def test_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SQLiteStore(db_path)
        doc = Document(
            title="Test Doc",
            content="This is test content.",
            source_type="paste"
        )
        saved_doc = store.add_document(doc)
        assert saved_doc.id is not None
        assert saved_doc.content_hash is not None

        chunks = [
            Chunk(
                id=f"{saved_doc.id}-c0000",
                document_id=saved_doc.id,
                text="chunk 1",
                ordinal=0
            ),
            Chunk(
                id=f"{saved_doc.id}-c0001",
                document_id=saved_doc.id,
                text="chunk 2",
                ordinal=1
            )
        ]
        saved_chunks = store.add_chunks(chunks)
        assert len(saved_chunks) == 2
        assert all(c.id is not None for c in saved_chunks)

        retrieved_chunks = store.get_chunks_by_document_id(saved_doc.id)
        assert len(retrieved_chunks) == 2
    finally:
        os.unlink(db_path)
