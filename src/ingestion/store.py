
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from .dedupe import Deduplicator
from .schema import Chunk, Document


class SQLiteStore:
    """SQLite-backed storage for ingested documents and chunks."""

    def __init__(self, db_path: str = "ingestion.db") -> None:
        """Initialize the store and create tables if they do not exist.

        Args:
            db_path:
                SQLite database file path (or special URI).
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    file_type TEXT,
                    created_at TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    start_char INTEGER,
                    end_char INTEGER,
                    session_id TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents (id)
                )
                """
            )

            conn.commit()
        finally:
            conn.close()

    def add_document(self, document: Document) -> Document:
        """Persist a document, returning the existing copy if already ingested.

        Args:
            document:
                Unsaved document model.

        Returns:
            Saved (possibly existing) document.
        """
        content_hash = Deduplicator.compute_hash(document.content)
        existing_doc = self.get_document_by_hash(content_hash)
        if existing_doc:
            return existing_doc

        document.id = str(uuid.uuid4())
        document.content_hash = content_hash
        document.created_at = datetime.now()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (id, title, content, source_type, file_type, created_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.title,
                    document.content,
                    document.source_type,
                    document.file_type,
                    document.created_at.isoformat(),
                    document.content_hash,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return document

    def get_document_by_hash(self, content_hash: str) -> Document | None:
        """Look up a document by its content hash.

        Args:
            content_hash:
                SHA-256 hash string.

        Returns:
            Document or None.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE content_hash = ?", (content_hash,))
            row = cursor.fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        return Document(
            id=row[0],
            title=row[1],
            content=row[2],
            source_type=row[3],
            file_type=row[4],
            created_at=datetime.fromisoformat(row[5]),
            content_hash=row[6],
        )

    def add_chunks(self, chunks: list[Chunk], replace: bool = True) -> list[Chunk]:
        """Persist chunks, optionally replacing prior chunks for the document.

        Args:
            chunks:
                Chunk records to insert.
            replace:
                When True, delete prior chunks belonging to the same document first.

        Returns:
            The same chunk list.
        """
        if not chunks:
            return chunks

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            if replace:
                cursor.execute(
                    "DELETE FROM chunks WHERE document_id = ?",
                    (chunks[0].document_id,),
                )

            for chunk in chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (id, document_id, text, ordinal, start_char, end_char, session_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.text,
                        chunk.ordinal,
                        chunk.start_char,
                        chunk.end_char,
                        chunk.session_id,
                    ),
                )

            conn.commit()
        finally:
            conn.close()
        return chunks

    def get_chunks_by_document_id(self, document_id: str) -> list[Chunk]:
        """Return all chunks for a document ordered by ordinal.

        Args:
            document_id:
                Parent document identifier.

        Returns:
            Chunk list.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal",
                (document_id,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [
            Chunk(
                id=row[0],
                document_id=row[1],
                text=row[2],
                ordinal=row[3],
                start_char=row[4],
                end_char=row[5],
                session_id=row[6],
            )
            for row in rows
        ]
