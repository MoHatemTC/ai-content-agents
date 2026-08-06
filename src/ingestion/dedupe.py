from __future__ import annotations

import hashlib


class Deduplicator:
    """Compute stable content fingerprints for dedupe decisions."""

    @staticmethod
    def compute_hash(content: str) -> str:
        """Return a SHA-256 hex digest of the cleaned content.

        Args:
            content:
                Cleaned document text.

        Returns:
            64-character hex hash.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
