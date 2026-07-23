
from __future__ import annotations

import re


class TextCleaner:
    @staticmethod
    def clean(text: str) -> str:
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        # Normalize line breaks
        text = re.sub(r'\n+', '\n', text)
        return text
