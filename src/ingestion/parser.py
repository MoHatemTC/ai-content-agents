
from __future__ import annotations

import io
import re
import markdown


class TextParser:
    @staticmethod
    def parse_txt(file_content: bytes) -> str:
        return file_content.decode('utf-8', errors='replace')

    @staticmethod
    def parse_pdf(file_content: bytes) -> str:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_content, filetype='pdf')
            text = []
            for page in doc:
                text.append(page.get_text())
            return '\n'.join(text)
        except ImportError:
            raise ImportError("PyMuPDF is required for PDF parsing. Install it with 'pip install pymupdf'.")

    @staticmethod
    def parse_docx(file_content: bytes) -> str:
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_content))
            text = []
            for para in doc.paragraphs:
                text.append(para.text)
            return '\n'.join(text)
        except ImportError:
            raise ImportError("python-docx is required for DOCX parsing. Install it with 'pip install python-docx'.")

    @staticmethod
    def parse_markdown(file_content: bytes) -> str:
        md_text = file_content.decode('utf-8', errors='replace')
        # Convert markdown to plain text by stripping HTML tags
        html = markdown.markdown(md_text)
        # Simple HTML tag stripping
        plain_text = re.sub(r'<[^>]*>', '', html)
        return plain_text

    @classmethod
    def parse(cls, file_content: bytes, file_type: str) -> str:
        parsers = {
            'txt': cls.parse_txt,
            'pdf': cls.parse_pdf,
            'docx': cls.parse_docx,
            'md': cls.parse_markdown
        }
        if file_type not in parsers:
            raise ValueError(f"Unsupported file type: {file_type}")
        return parsers[file_type](file_content)
