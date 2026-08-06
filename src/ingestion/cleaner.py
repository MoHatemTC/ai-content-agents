from __future__ import annotations

import re


class TextCleaner:
    """Normalize raw extracted text before chunking."""

    @staticmethod
    def clean(text: str) -> str:
        """Collapse all whitespace runs into single spaces.

        Note this flattens the document onto one line: newlines are whitespace,
        so paragraph structure does not survive. That is the established
        behaviour and ``test_text_cleaner`` asserts it.

        Args:
            text:
                Raw extracted text.

        Returns:
            Cleaned text.
        """
        return re.sub(r"\s+", " ", text).strip()
