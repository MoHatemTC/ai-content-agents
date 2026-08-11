from __future__ import annotations

import io
import re

import markdown


class TextParser:
    """Extract raw text from common document formats."""

    @staticmethod
    def parse_txt(file_content: bytes) -> str:
        """Decode UTF-8 text bytes.

        Args:
            file_content:
                Raw file bytes.

        Returns:
            Decoded text.
        """
        return file_content.decode("utf-8", errors="replace")

    @staticmethod
    def parse_pdf(file_content: bytes) -> str:
        """Extract text from a PDF document.

        Args:
            file_content:
                Raw PDF bytes.

        Returns:
            Concatenated page text.

        Raises:
            ImportError:
                If PyMuPDF is not installed.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(
                "PyMuPDF is required for PDF parsing. Install it with 'pip install pymupdf'."
            ) from exc

        doc = fitz.open(stream=file_content, filetype="pdf")
        try:
            pages = [page.get_text() for page in doc]
        finally:
            doc.close()
        return "\n".join(pages)

    @staticmethod
    def parse_docx(file_content: bytes) -> str:
        """Extract paragraph text from a DOCX document.

        Args:
            file_content:
                Raw DOCX bytes.

        Returns:
            Concatenated paragraph text.

        Raises:
            ImportError:
                If python-docx is not installed.
        """
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(
                "python-docx is required for DOCX parsing. Install it with 'pip install python-docx'."
            ) from exc

        doc = Document(io.BytesIO(file_content))
        return "\n".join(para.text for para in doc.paragraphs)

    @staticmethod
    def parse_markdown(file_content: bytes) -> str:
        """Convert Markdown to plain text by rendering then stripping HTML.

        Args:
            file_content:
                Raw Markdown bytes.

        Returns:
            Plain text.
        """
        md_text = file_content.decode("utf-8", errors="replace")
        html = markdown.markdown(md_text)
        return re.sub(r"<[^>]*>", "", html)

    @classmethod
    def parse(cls, file_content: bytes, file_type: str) -> str:
        """Dispatch parsing to the appropriate format-specific extractor.

        Args:
            file_content:
                Raw file bytes.
            file_type:
                Lowercase extension-style type.

        Returns:
            Extracted raw text.

        Raises:
            ValueError:
                If the file type is unsupported.
        """
        parsers = {
            "txt": cls.parse_txt,
            "pdf": cls.parse_pdf,
            "docx": cls.parse_docx,
            "md": cls.parse_markdown,
        }
        if file_type not in parsers:
            raise ValueError(f"Unsupported file type: {file_type}")
        return parsers[file_type](file_content)
