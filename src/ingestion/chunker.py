
from __future__ import annotations
import re

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
        chunks = []
        ordinal = 0

        for start, end in self._pack_sentences(text):

            if end - start <= self.chunk_size + 1:


              actual_start = start

              if chunks:
                  actual_start = max(0, start - self.overlap)
                  actual_start = self._adjust_start_to_word_boundary(
                      text,
                      actual_start,
                  )

              chunk_id = f"{document_id}-c{ordinal:04d}"

              chunks.append(
                   Chunk(
                       id=chunk_id,
                       document_id=document_id,
                       text=text[actual_start:end],
                       ordinal=ordinal,
                       start_char=actual_start,
                       end_char=end,
                       session_id=session_id,
                    )
                )

              ordinal += 1
  
            else:

              spans = self._split_long_sentence(
                text,
                start,
                end,
              )

              for sub_start, sub_end in spans:

                chunk_id = f"{document_id}-c{ordinal:04d}"

                chunks.append(
                    Chunk(
                        id=chunk_id,
                        document_id=document_id,
                        text=text[sub_start:sub_end],
                        ordinal=ordinal,
                        start_char=sub_start,
                        end_char=sub_end,
                        session_id=session_id,
                    )
                )

                ordinal += 1

        return chunks
    
    def _adjust_end_to_word_boundary(
        self,
        text: str,
        start: int,
        end: int,
    ) -> int:

       if end >= len(text):
           return len(text)

       original_end = end

       while (
              end > start 
              and not text[end-1].isspace()
              and text[end-1] not in ".!?"
       ):
            end -= 1

       if end == start:
           return original_end

       return end

    def _adjust_start_to_word_boundary(
        self,
        text: str,
        start: int,
    ) -> int:
        """
        Move the chunk start backward so it begins at the start of a word.
        """

        original_start = start

        while start > 0 and not text[start - 1].isspace():
           start -= 1

        # If there are no spaces (or we backed up too far),
        # keep the original overlap position.
        if start == 0 and not text[0].isspace():
            return original_start

        return start


    def _split_sentences(
        self,
        text: str,
    ) -> list[tuple[int, int]]:
        """
        Return (start, end) offsets for each sentence.
        """

        sentence_pattern = re.compile(
            r".+?(?:[.!?](?:\s+|$)|$)",
            re.DOTALL,
        )

        spans = []

        for match in sentence_pattern.finditer(text):
            start, end = match.span()

            while start < end and text[start].isspace():
                 start += 1

            while end > start and text[end - 1].isspace():
                end -= 1
    
            if start < end:
               spans.append((start, end))

        return spans

    def _pack_sentences(
        self,
        text: str,
    ) -> list[tuple[int, int]]:
        """
        Pack complete sentences into chunks without exceeding chunk_size.
        Returns (start, end) offsets.
        """

        sentence_spans = self._split_sentences(text)

        if not sentence_spans:
            return []

        packed = []

        current_start = sentence_spans[0][0]
        current_end = sentence_spans[0][1]

        for start, end in sentence_spans[1:]:

            if end - current_start <= self.chunk_size:
                current_end = end
            else:
               packed.append((current_start, current_end))
               current_start = start
               current_end = end

            

        packed.append((current_start, current_end))

        return packed


    def _split_long_sentence(
        self,
        text: str,
        start: int,
        end: int,
    ) -> list[tuple[int, int]]:
        """
        Split one oversized sentence on word boundaries.
        """

        spans = []

        current = start

        while current < end:

            raw_end = min(current + self.chunk_size, end)

            adjusted_end = self._adjust_end_to_word_boundary(
                text,
                current,
                raw_end,
            )
            

            if adjusted_end <= current:
                adjusted_end = raw_end

            spans.append((current, adjusted_end))

            if adjusted_end >= end:
                break

            next_start = max(start, adjusted_end - self.overlap)
            next_start = self._adjust_start_to_word_boundary(text, next_start)

            if next_start <= current:
                  next_start = adjusted_end

            current = next_start    

        return spans