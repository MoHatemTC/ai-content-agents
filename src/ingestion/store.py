from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from .dedupe import Deduplicator
from .schema import Chunk, Document


class SQLiteStore:
    """
    SQLite-based persistence layer for storing and retrieving
    ingested documents and their corresponding chunks.
    """

    def __init__(self, db_path: str = "ingestion.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_type TEXT NOT NULL,
                file_type TEXT,
                created_at TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
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
        """)

        conn.commit()
        conn.close()

    def add_document(self, document: Document) -> Document:
        content_hash = Deduplicator.compute_hash(document.content)
        existing_doc = self.get_document_by_hash(content_hash)
        if existing_doc:
            return existing_doc

        document.id = str(uuid.uuid4())
        document.content_hash = content_hash
        document.created_at = datetime.now()

        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        return document

    def get_document_by_hash(self, content_hash: str) -> Document | None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM documents WHERE content_hash = ?", (content_hash,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return Document(
                id=row[0],
                title=row[1],
                content=row[2],
                source_type=row[3],
                file_type=row[4],
                created_at=datetime.fromisoformat(row[5]),
                content_hash=row[6],
            )
        return None

    def add_chunks(self, chunks: list[Chunk], replace: bool = True) -> list[Chunk]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if replace and chunks:
            document_id = chunks[0].document_id
            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

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
        conn.close()
        return chunks

    def get_chunks_by_document_id(self, document_id: str) -> list[Chunk]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM chunks WHERE document_id = ?", (document_id,))
        rows = cursor.fetchall()
        conn.close()

        chunks = []
        for row in rows:
            chunks.append(
                Chunk(
                    id=row[0],
                    document_id=row[1],
                    text=row[2],
                    ordinal=row[3],
                    start_char=row[4],
                    end_char=row[5],
                    session_id=row[6],
                )
            )
        return chunks

    def get_all_documents(self) -> list[Document]:
        """
        Retrieve all stored documents ordered by creation date.

        Returns:
         A list of all documents in the database.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title, content, source_type,
                   file_type, created_at, content_hash
            FROM documents
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        documents = [
            Document(
                id=row[0],
                title=row[1],
                content=row[2],
                source_type=row[3],
                file_type=row[4],
                created_at=datetime.fromisoformat(row[5]),
                content_hash=row[6],
            )
            for row in rows
        ]

        return documents

    def get_document_by_id(self, document_id: str) -> Document | None:
        """
        Retrieve a document by its unique identifier.

        Args:
            document_id:
                The document ID.

        Returns:
            The matching document if found; otherwise ``None``.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, title, content, source_type,
                   file_type, created_at, content_hash
            FROM documents
            WHERE id = ?
        """,
            (document_id,),
        )

        row = cursor.fetchone()
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

    def count_chunks(self, document_id: str) -> int:
        """
        Count the number of chunks belonging to a document.

        Args:
            document_id:
                The document identifier.

        Returns:
            The total number of chunks.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM chunks
            WHERE document_id = ?
        """,
            (document_id,),
        )

        result = cursor.fetchone()
        count = result[0] if result else 0

        conn.close()

        return count

    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document and all of its chunks.

        Args:
            document_id:
                The identifier of the document to delete.

        Returns:
            ``True`` if the document existed and was deleted,
         otherwise ``False``.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

        cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    def document_exists(self, document_id: str) -> bool:
        """
        Check whether a document exists.

        Args:
            document_id:
                The document identifier.

        Returns:
            ``True`` if the document exists, otherwise ``False``.
        """
        return self.get_document_by_id(document_id) is not None
