"""Structure-aware chunking for retrieval.

Text is split using the coarsest structure that fits, descending only when a
unit is too large:

1. **Paragraphs** — blank-line separated, packed whole while they fit.
2. **Sentences** — packed within a paragraph too large to fit whole.
3. **Words** — a sentence longer than ``chunk_size`` is windowed on word
   boundaries.
4. **Characters** — a single *word* longer than ``chunk_size`` is hard-split.
   This is the progress guarantee; without it a long URL loops forever.

The chunker previously sliced raw character offsets, which cut words in half at
every boundary (``Convection`` became ``vection``) and put a corrupted token into
whatever was embedded and whatever a reviewer read as a citation.
"""

from __future__ import annotations

import re

from .schema import Chunk

# A sentence ends at .!? followed by whitespace - but only sometimes. These are
# the cases where it does not, and they matter here because study material is
# full of them: "See Fig. 21.5" and "Use e.g. water" are single sentences.
_ABBREVIATIONS = frozenset(
    [
        "fig",
        "figs",
        "eq",
        "eqs",
        "no",
        "nos",
        "vol",
        "ch",
        "chap",
        "sec",
        "ref",
        "refs",
        "p",
        "pp",
        "al",
        "etc",
        "vs",
        "cf",
        "approx",
        "dr",
        "mr",
        "mrs",
        "ms",
        "prof",
        "st",
        "jr",
        "sr",
        "inc",
        "ltd",
        "co",
        "dept",
        "est",
        "min",
        "max",
        "avg",
        "i.e",
        "e.g",
        "a.m",
        "p.m",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]
)

# The token immediately before a candidate boundary's period.
_TRAILING_TOKEN = re.compile(r"([A-Za-z][A-Za-z.]*)\.$")

# How far back to look for that token. The longest entry in _ABBREVIATIONS is
# five characters; 64 is generous and keeps the scan independent of document
# length, which is what stops sentence splitting being quadratic.
_ABBREVIATION_WINDOW = 64

# Candidate sentence boundary: a terminator followed by whitespace, or the end
# of the text. Decimals such as 0.375 are already excluded by requiring the
# whitespace - the period there is followed by a digit.
_BOUNDARY = re.compile(r"[.!?]+(?:\s+|$)")

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


class TextChunker:
    """Split cleaned text into stable retrieval chunks."""

    def __init__(self, chunk_size: int = 2000, overlap: int = 200) -> None:
        """Configure chunking behavior.

        Args:
            chunk_size:
                Maximum number of characters per chunk. This is a hard ceiling:
                the overlap carried from the previous chunk counts towards it.

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

    @property
    def _budget(self) -> int:
        """Characters of *new* content per chunk.

        Overlap is prepended to each chunk after packing, so packing to the full
        ``chunk_size`` would produce chunks of ``chunk_size + overlap`` and break
        the ceiling the constructor documents. Reserving the overlap up front is
        also what the original character chunker did, whose stride was
        ``chunk_size - overlap``.
        """
        return max(1, self.chunk_size - self.overlap)

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
            Ordered list of chunk records. ``text[start_char:end_char]`` always
            reproduces a chunk's text.
        """
        chunks: list[Chunk] = []
        ordinal = 0

        for start, end in self._pack(text):
            if end - start <= self.chunk_size:
                spans = [(self._with_overlap(text, start, end, bool(chunks)), end)]
            else:
                spans = self._split_long_sentence(text, start, end)

            for span_start, span_end in spans:
                chunks.append(
                    Chunk(
                        id=f"{document_id}-c{ordinal:04d}",
                        document_id=document_id,
                        text=text[span_start:span_end],
                        ordinal=ordinal,
                        start_char=span_start,
                        end_char=span_end,
                        session_id=session_id,
                    )
                )
                ordinal += 1

        return chunks

    # ------------------------------------------------------------------
    # Overlap
    # ------------------------------------------------------------------

    def _with_overlap(self, text: str, start: int, end: int, has_previous: bool) -> int:
        """Extend a chunk backwards to carry context from its predecessor.

        Args:
            text: The full document text.
            start: Where the packed unit begins.
            end: Where the packed unit ends.
            has_previous: Whether a chunk was already emitted; the first chunk
                has nothing to overlap with.

        Returns:
            The start offset to use, never further back than ``chunk_size``
            characters from ``end``.
        """
        if not has_previous or self.overlap == 0:
            return start

        actual_start = self._adjust_start_to_word_boundary(
            text, max(0, start - self.overlap)
        )

        # Backstop: snapping to a word boundary moves the start *backwards*, so
        # it can reach further back than the overlap asked for. The ceiling is a
        # promise, so give the overlap up rather than break it - and give it up
        # forwards, onto the next word, since cutting at a raw offset is the
        # mid-word defect this class exists to avoid.
        if end - actual_start > self.chunk_size:
            actual_start = self._advance_to_word_boundary(text, end - self.chunk_size)

        return min(actual_start, start)

    # ------------------------------------------------------------------
    # Boundary helpers
    # ------------------------------------------------------------------

    def _adjust_end_to_word_boundary(self, text: str, start: int, end: int) -> int:
        """Move ``end`` back so the chunk stops at the end of a word."""
        if end >= len(text):
            return len(text)

        original_end = end

        while (
            end > start and not text[end - 1].isspace() and text[end - 1] not in ".!?"
        ):
            end -= 1

        # A single word longer than the budget: keep the hard cut so the split
        # makes progress. This is level 4.
        if end == start:
            return original_end

        return end

    def _advance_to_word_boundary(self, text: str, start: int) -> int:
        """Move ``start`` forward to the beginning of the next whole word.

        The backward-looking sibling below would lengthen the chunk, which is
        the wrong direction when the point is to fit inside ``chunk_size``.
        """
        limit = len(text)

        while start < limit and not text[start].isspace():
            start += 1
        while start < limit and text[start].isspace():
            start += 1

        return start

    def _adjust_start_to_word_boundary(self, text: str, start: int) -> int:
        """Move ``start`` back so the chunk begins at the start of a word."""
        original_start = start

        while start > 0 and not text[start - 1].isspace():
            start -= 1

        # No whitespace to find: keep the requested position rather than
        # swallowing the whole document.
        if start == 0 and text and not text[0].isspace():
            return original_start

        return start

    # ------------------------------------------------------------------
    # Level 2: sentences
    # ------------------------------------------------------------------

    def _is_real_boundary(self, text: str, period_end: int, next_start: int) -> bool:
        """Decide whether a candidate terminator really ends a sentence.

        Args:
            text: The full document text.
            period_end: Offset just past the terminator.
            next_start: Offset of the next non-space character, or ``len(text)``.

        Returns:
            ``False`` when the terminator belongs to an abbreviation or an
            initial rather than to the end of a sentence.
        """
        if next_start >= len(text):
            return True

        # "Fig. 21.5" and "Use e.g. water": running text continues after the
        # period. A genuine new sentence starts with a capital or a quote.
        following = text[next_start]
        if following.islower() or following.isdigit():
            return False

        # Look only at the handful of characters before the period, not at the
        # whole prefix. `text[:period_end]` copies everything read so far on
        # every candidate boundary, which is O(n^2) over the document: a
        # 1,598-page textbook has ~60,000 boundaries, and splitting it took an
        # extrapolated 150 minutes. The pattern is anchored to the end of the
        # window, and no abbreviation approaches this length.
        window_start = max(0, period_end - _ABBREVIATION_WINDOW)
        match = _TRAILING_TOKEN.search(text[window_start:period_end])
        if match is None:
            return True

        # "Dr. Young" is followed by a capital, so only the list catches it.
        #
        # Single letters are deliberately *not* treated as initials here. It is
        # tempting - "J. R. R. Tolkien" - but study material ends sentences on
        # variables far more often than it names people by initial: "where
        # R = L / k." and "T = 2.27 C." both close on a lone letter. Splitting a
        # name into short fragments costs nothing, because packing puts them
        # straight back together; merging two real sentences coarsens every
        # chunk boundary that follows.
        return match.group(1).rstrip(".").lower() not in _ABBREVIATIONS

    def _split_sentences(self, text: str) -> list[tuple[int, int]]:
        """Return ``(start, end)`` offsets for each sentence."""
        spans: list[tuple[int, int]] = []
        cursor = 0

        for match in _BOUNDARY.finditer(text):
            # The terminator itself belongs to the sentence; the whitespace
            # that follows it does not.
            period_end = match.start() + len(match.group().rstrip())

            if not self._is_real_boundary(text, period_end, match.end()):
                continue

            span = self._trim(text, cursor, period_end)
            if span is not None:
                spans.append(span)

            cursor = match.end()

        tail = self._trim(text, cursor, len(text))
        if tail is not None:
            spans.append(tail)

        return spans

    @staticmethod
    def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
        """Strip surrounding whitespace from a span, or drop it if empty."""
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return (start, end) if start < end else None

    # ------------------------------------------------------------------
    # Levels 1 and 2: pack paragraphs, then sentences within them
    # ------------------------------------------------------------------

    def _paragraph_spans(self, text: str) -> list[tuple[int, int]]:
        """Return ``(start, end)`` offsets for each blank-line separated block."""
        spans: list[tuple[int, int]] = []
        cursor = 0

        for match in _PARAGRAPH_BREAK.finditer(text):
            span = self._trim(text, cursor, match.start())
            if span is not None:
                spans.append(span)
            cursor = match.end()

        span = self._trim(text, cursor, len(text))
        if span is not None:
            spans.append(span)

        return spans

    def _pack(self, text: str) -> list[tuple[int, int]]:
        """Pack whole paragraphs, descending to sentences where one is too big.

        Returns:
            ``(start, end)`` offsets, each within :attr:`_budget` unless it is a
            single sentence that cannot be packed any smaller.
        """
        packed: list[tuple[int, int]] = []
        buffer: tuple[int, int] | None = None

        for paragraph_start, paragraph_end in self._paragraph_spans(text):
            if paragraph_end - paragraph_start > self._budget:
                # Too big to keep whole: flush, then pack its sentences.
                if buffer is not None:
                    packed.append(buffer)
                    buffer = None
                packed.extend(
                    self._pack_sentences(text, paragraph_start, paragraph_end)
                )
            elif buffer is None:
                buffer = (paragraph_start, paragraph_end)
            elif paragraph_end - buffer[0] <= self._budget:
                buffer = (buffer[0], paragraph_end)
            else:
                packed.append(buffer)
                buffer = (paragraph_start, paragraph_end)

        if buffer is not None:
            packed.append(buffer)

        return packed

    def _pack_sentences(
        self,
        text: str,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, int]]:
        """Pack complete sentences without exceeding the per-chunk budget.

        Args:
            text: The full document text.
            start: Optional region start; defaults to the whole text.
            end: Optional region end; defaults to the whole text.

        Returns:
            ``(start, end)`` offsets, one per packed group of sentences.
        """
        region_start = 0 if start is None else start
        region_end = len(text) if end is None else end

        sentence_spans = [
            span
            for span in self._split_sentences(text[region_start:region_end])
            if span[0] < span[1]
        ]
        if not sentence_spans:
            return []

        # _split_sentences worked on a slice; shift the offsets back.
        sentence_spans = [
            (span_start + region_start, span_end + region_start)
            for span_start, span_end in sentence_spans
        ]

        packed: list[tuple[int, int]] = []
        current_start, current_end = sentence_spans[0]

        for span_start, span_end in sentence_spans[1:]:
            if span_end - current_start <= self._budget:
                current_end = span_end
            else:
                packed.append((current_start, current_end))
                current_start, current_end = span_start, span_end

        packed.append((current_start, current_end))

        return packed

    # ------------------------------------------------------------------
    # Levels 3 and 4: words, then characters
    # ------------------------------------------------------------------

    def _split_long_sentence(
        self,
        text: str,
        start: int,
        end: int,
    ) -> list[tuple[int, int]]:
        """Split one oversized sentence on word boundaries."""
        spans: list[tuple[int, int]] = []
        current = start

        while current < end:
            raw_end = min(current + self.chunk_size, end)

            adjusted_end = self._adjust_end_to_word_boundary(text, current, raw_end)

            if adjusted_end <= current:
                adjusted_end = raw_end

            spans.append((current, min(adjusted_end, end)))

            if adjusted_end >= end:
                break

            next_start = max(start, adjusted_end - self.overlap)
            next_start = self._adjust_start_to_word_boundary(text, next_start)

            if next_start <= current:
                next_start = adjusted_end

            current = next_start

        return spans
