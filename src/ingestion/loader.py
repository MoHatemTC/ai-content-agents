from __future__ import annotations

import logging

from .chunker import TextChunker
from .cleaner import TextCleaner
from .ocr import (
    ocr_availability,
    ocr_enabled,
    ocr_looks_readable,
    ocr_pdf,
    strip_scanner_furniture,
)
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

    def _recover_scanned_pdf(self, file_content: bytes) -> tuple[str, str]:
        """Recover text from a PDF that has no text layer, or explain why we cannot.

        A PDF with no text layer is a scan or a photo export. Nothing can read
        characters that were never stored, so the only route is recognition - and
        that comes in two kinds, because Tesseract reads printed characters and
        cannot read handwriting. On a handwritten page it does not fail; it
        returns nonsense through the same interface as success, which is how a
        scan of physics notes once became flashcards titled "CamScanner".

        So the output is judged before it is accepted. When it does not read as
        language, a vision model is asked to transcribe the pages instead - and
        when that is switched off, the user is told what the document actually is
        rather than being handed the noise.

        Args:
            file_content: The raw PDF bytes.

        Returns:
            A ``(text, method)`` pair, where ``method`` is ``"ocr"`` or
            ``"vision-ocr"`` and records how the text came to exist.

        Raises:
            ValueError: If recognition is disabled, unavailable, or produced
                nothing usable.
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
        recovered = strip_scanner_furniture(ocr_pdf(file_content))

        if recovered.strip():
            readable, why = ocr_looks_readable(recovered)
            if readable:
                return recovered, "ocr"
            logger.info("OCR output rejected: %s", why)
        else:
            why = (
                "OCR recognised no text at all - the scan may be blank or too "
                "low-resolution."
            )

        return self._transcribe_with_vision(file_content, base, why)

    def _transcribe_with_vision(
        self, file_content: bytes, base: str, ocr_failure: str
    ) -> tuple[str, str]:
        """Ask a vision model to read pages conventional OCR could not.

        Args:
            file_content: The raw PDF bytes.
            base: Shared prefix describing the document, for error messages.
            ocr_failure: Why the Tesseract pass was rejected, so the user hears
                the actual diagnosis rather than a generic failure.

        Returns:
            A ``(text, "vision-ocr")`` pair.

        Raises:
            ValueError: If vision transcription is off, unavailable, or returned
                nothing.
        """
        from .vision_ocr import (
            VisionOcrUnavailableError,
            transcribe_pdf,
            vision_ocr_availability,
            vision_ocr_enabled,
        )

        if not vision_ocr_enabled():
            raise ValueError(
                f"{base}, and {ocr_failure} Set ENABLE_VISION_OCR=true to "
                "transcribe it with a vision model instead, or paste the text on "
                "the Paste Text tab."
            )

        available, reason = vision_ocr_availability()
        if not available:
            raise ValueError(
                f"{base}, and {ocr_failure} Vision transcription cannot run "
                f"because {reason}."
            )

        logger.info("escalating to vision transcription")
        try:
            transcribed = transcribe_pdf(file_content)
        except VisionOcrUnavailableError as exc:
            raise ValueError(f"{base}. {exc}") from exc

        if not transcribed.strip():
            raise ValueError(
                f"{base}, and {ocr_failure} A vision model was asked to "
                "transcribe it and found no educational content either."
            )

        return transcribed, "vision-ocr"

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
            raw_text, method = self._recover_scanned_pdf(file_content)
            # Record how the text came to exist. Extracted text is evidence a
            # human supplied; a vision transcription is a reconstruction, and a
            # reviewer needs to be able to tell which one they are citing.
            source_type = f"{source_type}-{method}"

        cleaned_text = self.cleaner.clean(raw_text)

        result = self.quality.validate(cleaned_text)

        if not result.passed:
            raise ValueError("Quality check failed:\n" + "\n".join(result.issues))

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
            raise ValueError("Quality check failed:\n" + "\n".join(result.issues))

        document = Document(
            title=title,
            content=cleaned_text,
            source_type=source_type,
        )

        saved_doc = self.store.add_document(document)
        chunks = self.chunker.chunk(saved_doc.content, saved_doc.id, session_id)
        self.store.add_chunks(chunks)

        return saved_doc
