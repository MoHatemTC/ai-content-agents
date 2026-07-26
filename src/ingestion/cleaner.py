
from __future__ import annotations

import re


class TextCleaner:
    """Normalize raw extracted text before chunking."""

    @staticmethod
    def clean(text: str) -> str:
        """Collapse whitespace and normalize line breaks.

        Args:
            text:
                Raw extracted text.

        Returns:
            Cleaned text.
        """
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove leading/trailing whitespace
        text = text.strip()
        # Normalize line breaks
        text = re.sub(r"\n+", "\n", text)
        return text
