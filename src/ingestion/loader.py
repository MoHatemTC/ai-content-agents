
from __future__ import annotations

from .chunker import TextChunker
from .cleaner import TextCleaner
from .parser import TextParser
from .schema import Document
from .store import SQLiteStore
from .quality import QualityChecker


class ContentLoader:
    """High level entry-point for ingesting files and text into the store."""

    def __init__(self, db_path: str = "ingestion.db") -> None:
        """Wire the pipeline components.

        Args:
            db_path:
                SQLite DB path forwarded to the store.
        """
        self.store = SQLiteStore(db_path)
        self.cleaner = TextCleaner()
        self.chunker = TextChunker()
        self.quality = QualityChecker()

    def load_file(
        self,
        file_content: bytes,
        filename: str,
        source_type: str = "file",
        session_id: str | None = None,
    ) -> Document:
        """Parse, clean, persist, and chunk a raw file.

        Args:
            file_content:
                Raw bytes.
            filename:
                Original filename (used for title and type detection).
            source_type:
                Stored source type (e.g. 'file').
            session_id:
                Optional session scope propagated to chunks.

        Returns:
            Saved document.
        """
        file_type = filename.split(".")[-1].lower() if "." in filename else None

        raw_text = TextParser.parse(file_content, file_type)
        cleaned_text = self.cleaner.clean(raw_text)

        result = self.quality.validate(cleaned_text)

        if not result.passed:
            raise ValueError(
                "Quality check failed:\n" +
                "\n".join(result.issues)
            )

        document = Document(
            title=filename,
            content=cleaned_text,
            source_type=source_type,
            file_type=file_type,
        )

        saved_doc = self.store.add_document(document)
        chunks = self.chunker.chunk(saved_doc.content, saved_doc.id, session_id)
        self.store.add_chunks(chunks)

        return saved_doc

    def load_text(
        self,
        text: str,
        title: str = "Pasted Text",
        source_type: str = "paste",
        session_id: str | None = None,
    ) -> Document:
        """Clean, persist, and chunk pasted/plain text.

        Args:
            text:
                Plain text input.
            title:
                Stored document title.
            source_type:
                Stored source type (e.g. 'paste').
            session_id:
                Optional session scope propagated to chunks.

        Returns:
            Saved document.
        """
        cleaned_text = self.cleaner.clean(text)
        result = self.quality.validate(cleaned_text)

        if not result.passed:
            raise ValueError(
                "Quality check failed:\n" +
                "\n".join(result.issues)
            )

        document = Document(
            title=title,
            content=cleaned_text,
            source_type=source_type,
        )

        saved_doc = self.store.add_document(document)
        chunks = self.chunker.chunk(saved_doc.content, saved_doc.id, session_id)
        self.store.add_chunks(chunks)

        return saved_doc
