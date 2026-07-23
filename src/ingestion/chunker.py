
from __future__ import annotations

from .schema import Chunk


class TextChunker:
    """Split cleaned text into stable retrieval chunks."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 100) -> None:
        """Configure chunking behavior.

        Args:
            chunk_size:
                Maximum number of characters per chunk.

            overlap:
                Number of characters to carry into the next chunk.
        """
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than zero")

        if overlap < 0:
            raise ValueError("Overlap must be zero or greater")

        if overlap >= chunk_size:
            raise ValueError("Overlap must be less than chunk size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(
        self,
        text: str,
        document_id: str,
        session_id: str | None = None,
    ) -> list[Chunk]:
        """Return stable chunks for the given document text.

        Args:
            text:
                Cleaned document text.

            document_id:
                Parent document identifier.

            session_id:
                Optional retrieval session scope.

        Returns:
            Ordered list of chunk records.
        """
        chunks: list[Chunk] = []
        start = 0
        ordinal = 0
        text_length = len(text)
        stride = self.chunk_size - self.overlap

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_id = f"{document_id}-c{ordinal:04d}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    document_id=document_id,
                    text=text[start:end],
                    ordinal=ordinal,
                    start_char=start,
                    end_char=end,
                    session_id=session_id,
                )
            )

            if end == text_length:
                break

            start += stride
            ordinal += 1

        return chunks
