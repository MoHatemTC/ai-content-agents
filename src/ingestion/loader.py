
from __future__ import annotations

import logging

from .chunker import TextChunker
from .cleaner import TextCleaner
from .ocr import ocr_availability, ocr_enabled, ocr_pdf
from .parser import TextParser
from .quality import QualityChecker
from .schema import Document
from .store import SQLiteStore

logger = logging.getLogger(__name__)


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

    def _recover_scanned_pdf(self, file_content: bytes) -> str:
        """Try OCR on a PDF that yielded no text, or explain why we cannot.

        A PDF with no text layer is a scan or a photo export. Nothing can read
        characters that were never stored, so the only route is OCR - and that
        needs a system binary we cannot assume exists. When it is unavailable
        the user gets a message naming the cause and a workaround, rather than
        the misleading "Document is empty".

        Args:
            file_content: The raw PDF bytes.

        Returns:
            Text recovered by OCR.

        Raises:
            ValueError: If OCR is disabled, unavailable, or recovered nothing.
        """
        base = (
            "No text could be extracted from this PDF. It appears to be a "
            "scanned or image-only document"
        )

        if not ocr_enabled():
            raise ValueError(
                f"{base}, and OCR is switched off. Set ENABLE_OCR=true to try "
                "OCR, or paste the text on the Paste Text tab."
            )

        available, reason = ocr_availability()
        if not available:
            raise ValueError(f"{base}, and OCR cannot run because {reason}")

        logger.info("no text layer found; falling back to OCR")
        recovered = ocr_pdf(file_content)

        if not recovered.strip():
            raise ValueError(
                f"{base}. OCR ran but recognised no text - the scan may be too "
                "low-resolution, blank, or in a language Tesseract lacks data for."
            )
        return recovered

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

        if file_type == "pdf" and not raw_text.strip():
            raw_text = self._recover_scanned_pdf(file_content)

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
