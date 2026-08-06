"""Tests for the structure-aware chunker.

The chunker is the foundation of retrieval: a chunk is what gets embedded, what
gets returned, and what a reviewer reads as a citation. These tests cover the
acceptance criteria from issue #18, including the four that a green suite failed
to catch the first time round.
"""

import time

import pytest

from src.ingestion.chunker import TextChunker
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import split_text_into_chunks

# Transcribed from a real page of handwritten physics notes. Study material is
# full of decimals and abbreviations, and both are traps for a sentence splitter.
REAL_PHYSICS = (
    "Assignment (Mechanism of heat transfer). "
    "H = A (T_H - T_C) / R where R = L / k. "
    "R_wood = (0.03 x 10^-2) / 0.08 = 0.375 and R_styrofoam = 0.275. "
    "See Fig. 21.5 for the arrangement of the two slabs. "
    "Solving gives 0.65T = 1.475, i.e. T = 2.27 C. "
    "Dr. Young derives the same result in Ch. 17 using conductivity k = 50.2."
)

PROSE = (
    "Conduction moves energy through a material by direct molecular contact. "
    "Convection carries heat in the bulk motion of a fluid. "
    "Radiation needs no medium at all: energy crosses a vacuum as waves. "
) * 12


def test_chunks_do_not_split_words():
    text = (
        "Conduction transfers heat through direct molecular contact. "
        "Convection carries heat in the bulk motion of a fluid. "
        "Radiation transfers energy through electromagnetic waves."
    )

    chunker = TextChunker(chunk_size=60, overlap=10)
    chunks = chunker.chunk(text, "doc")

    for chunk in chunks:
        # chunk should not begin with the second half of a word
        assert not (
            chunk.text
            and chunk.text[0].isalnum()
            and chunk.start_char > 0
            and text[chunk.start_char - 1].isalnum()
        )

        # chunk should not end in the middle of a word
        if chunk.end_char < len(text):
            assert text[chunk.end_char].isspace()


def test_overlap_is_preserved():
    text = (
        "This is sentence one. "
        "This is sentence two. "
        "This is sentence three. "
        "This is sentence four."
    )

    chunker = TextChunker(chunk_size=40, overlap=10)
    chunks = chunker.chunk(text, "doc")

    assert len(chunks) > 1

    first = chunks[0].text
    second = chunks[1].text

    overlap = first[-10:]

    assert overlap in second


def test_long_word_does_not_loop():
    text = "a" * 3000

    chunker = TextChunker(chunk_size=1000, overlap=100)
    chunks = chunker.chunk(text, "doc")

    assert len(chunks) > 0


def test_sentence_split():
    chunker = TextChunker()

    text = "Sentence one. Sentence two! Sentence three?"

    spans = chunker._split_sentences(text)

    sentences = [text[s:e] for s, e in spans]

    assert sentences == [
        "Sentence one.",
        "Sentence two!",
        "Sentence three?",
    ]


def test_sentence_packing():
    chunker = TextChunker(chunk_size=40, overlap=10)

    text = "Sentence one. Sentence two. Sentence three."

    spans = chunker._pack_sentences(text)

    chunks = [text[s:e] for s, e in spans]

    assert chunks == [
        "Sentence one. Sentence two.",
        "Sentence three.",
    ]


def test_long_sentence_is_split():
    chunker = TextChunker(
        chunk_size=40,
        overlap=10,
    )

    text = (
        "This is one extremely long sentence that should be split into "
        "multiple chunks while preserving complete words throughout."
    )

    spans = chunker._split_long_sentence(
        text,
        0,
        len(text),
    )

    chunks = [text[s:e] for s, e in spans]

    assert len(chunks) > 1

    for start, end in spans:
        if end < len(text):
            assert text[end - 1].isspace() or text[end - 1] in ".!?"


# --------------------------------------------------------------------------- #
# chunk_size is a ceiling, not a target
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(200, 50), (1000, 100), (60, 10), (120, 0)],
)
def test_no_chunk_exceeds_chunk_size(chunk_size: int, overlap: int) -> None:
    """The docstring calls chunk_size a maximum, so it has to be one.

    Overlap used to be prepended *after* packing had already filled to the
    limit, so the real ceiling was chunk_size + overlap - 23% over at the
    defaults. If chunk_size is ever tuned to an embedding window, that overflow
    truncates silently.
    """
    chunks = TextChunker(chunk_size=chunk_size, overlap=overlap).chunk(PROSE, "doc")

    oversized = [(c.id, len(c.text)) for c in chunks if len(c.text) > chunk_size]
    assert not oversized, f"{len(oversized)} chunks over {chunk_size}: {oversized[:3]}"


def test_overlap_is_still_carried_despite_the_ceiling() -> None:
    """Enforcing the ceiling must not quietly drop the overlap instead.

    The two pull against each other: packing to the full chunk_size and then
    prepending the overlap would breach the ceiling, while clamping to the
    ceiling afterwards would leave no room for any overlap at all. Reserving the
    overlap up front is what satisfies both.

    Every sentence here is unique, because with repeated text "these two chunks
    share a word" is true whether or not any overlap was carried.
    """
    text = " ".join(f"Sentence {i} discusses topic{i} in detail." for i in range(40))
    chunks = TextChunker(chunk_size=200, overlap=50).chunk(text, "doc")

    assert len(chunks) > 2
    for previous, current in zip(chunks, chunks[1:]):
        carried = text[current.start_char : previous.end_char]
        assert carried, f"{current.id} carries nothing from {previous.id}"
        assert carried in previous.text


# --------------------------------------------------------------------------- #
# Sentence boundaries on real study material
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    ["Fig. 21.5", "i.e. T = 2.27 C", "Dr. Young", "Ch. 17", "0.375", "0.03 x 10^-2"],
)
def test_abbreviations_and_decimals_are_not_split(phrase: str) -> None:
    """A period followed by a space does not always end a sentence.

    "See Fig. 21.5" used to be severed across two chunks, which puts half a
    figure reference in one citation and half in another.
    """
    chunks = TextChunker(chunk_size=90, overlap=0).chunk(REAL_PHYSICS, "phys")

    assert any(phrase in c.text for c in chunks), [c.text for c in chunks]


@pytest.mark.parametrize(
    "sentence",
    [
        "Measured at 90 deg. celsius throughout the run.",
        "See Tbl. 4 for the recorded values.",
        "The first and second cases resp. behave alike.",
    ],
)
def test_unlisted_abbreviations_are_protected_by_the_general_rule(
    sentence: str,
) -> None:
    """The word list cannot enumerate every abbreviation, so it is not the only
    defence: running text after a period - a lowercase word or a digit - means
    the sentence continues.

    ``deg.``, ``Tbl.`` and ``resp.`` are deliberately absent from the list.
    """
    spans = TextChunker()._split_sentences(sentence)

    assert len(spans) == 1, [sentence[s:e] for s, e in spans]


def test_real_sentences_still_split() -> None:
    """The abbreviation guard must not swallow genuine sentence boundaries."""
    spans = TextChunker()._split_sentences(REAL_PHYSICS)

    assert len(spans) >= 5, [REAL_PHYSICS[s:e] for s, e in spans]


# --------------------------------------------------------------------------- #
# Paragraphs are the outermost level
# --------------------------------------------------------------------------- #


def test_paragraphs_are_packed_whole_not_torn_at_sentences() -> None:
    """Paragraph structure outranks sentence packing.

    Each paragraph here holds two sentences and the budget fits three, so a
    sentence-only chunker would pull the first sentence of the second paragraph
    up into the first chunk. Packing paragraphs whole keeps them together.
    """
    text = (
        "Alpha one here. Alpha two here.\n\n"
        "Beta one here. Beta two here.\n\n"
        "Gamma one here. Gamma two here."
    )
    chunks = TextChunker(chunk_size=48, overlap=0).chunk(text, "doc")

    for chunk in chunks:
        letters = {word[0] for word in chunk.text.split() if word[0].isalpha()}
        assert len(letters & {"A", "B", "G"}) <= 1, (
            f"chunk mixes paragraphs: {chunk.text!r}"
        )


def test_a_paragraph_larger_than_the_budget_falls_back_to_sentences() -> None:
    """Level 1 must descend to level 2, not give up and emit an oversized chunk."""
    paragraph = " ".join(f"Sentence number {i} of the paragraph." for i in range(12))
    chunks = TextChunker(chunk_size=100, overlap=10).chunk(paragraph, "doc")

    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)


# --------------------------------------------------------------------------- #
# Offsets, agreement, determinism
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", [PROSE, REAL_PHYSICS, "One.\n\nTwo.\n\nThree."])
def test_offsets_reproduce_the_chunk(text: str) -> None:
    """start_char/end_char are persisted, so they have to mean something."""
    chunks = TextChunker(chunk_size=120, overlap=20).chunk(text, "doc")

    for chunk in chunks:
        assert text[chunk.start_char : chunk.end_char] == chunk.text


def test_both_entry_points_produce_identical_chunks() -> None:
    """The reason issue #18 existed.

    Ingestion and retrieval both mint ids in the {document_id}-c{ordinal}
    namespace. While they chunked differently, "doc-c0001" denoted different
    text depending on which one ran - so a chunk id was not an identifier at
    all, in a project built on grounded citation.
    """
    config = RetrievalConfig(chunk_size=200, chunk_overlap=50)

    ingestion = TextChunker(chunk_size=200, overlap=50).chunk(PROSE, "doc")
    retrieval = split_text_into_chunks(PROSE, document_id="doc", config=config)

    assert [c.text for c in ingestion] == [c.text for c in retrieval]
    assert [c.id for c in ingestion] == [c.chunk_id for c in retrieval]


def test_chunking_is_deterministic() -> None:
    """Stored citations depend on the same document chunking the same way."""
    first = TextChunker().chunk(REAL_PHYSICS, "doc")
    second = TextChunker().chunk(REAL_PHYSICS, "doc")

    assert [(c.id, c.text, c.start_char) for c in first] == [
        (c.id, c.text, c.start_char) for c in second
    ]


@pytest.mark.parametrize("text", ["", "   ", "\n\n  \n\n", "\t"])
def test_empty_input_yields_no_chunks(text: str) -> None:
    assert TextChunker().chunk(text, "doc") == []


def test_ordinals_are_contiguous() -> None:
    """Ids are formatted from the ordinal, so a gap would be a broken citation."""
    chunks = TextChunker(chunk_size=90, overlap=15).chunk(PROSE, "doc")

    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert [c.id for c in chunks] == [f"doc-c{i:04d}" for i in range(len(chunks))]


# --------------------------------------------------------------------------- #
# Cost has to stay linear in document length
# --------------------------------------------------------------------------- #


def test_a_large_document_chunks_in_reasonable_time() -> None:
    """Guards against per-boundary work that scans the whole document.

    The abbreviation check originally searched ``text[:period_end]`` — a copy of
    everything read so far — on every candidate sentence boundary. That is
    O(n^2): every fixture in this file is small enough to hide it, while a
    1,598-page textbook took an extrapolated **150 minutes** to split.

    The bound is deliberately loose. It is not a benchmark; it is the difference
    between linear and quadratic, which for this input is roughly 0.05s against
    200s, so a slow CI runner cannot make it flake.
    """
    text = (
        "Conduction moves energy through a material by direct molecular contact. "
        "See Fig. 21.5 for the arrangement. Convection carries heat in a fluid. "
    ) * 7000  # ~1 MB

    start = time.perf_counter()
    chunks = TextChunker().chunk(text, "big")
    elapsed = time.perf_counter() - start

    assert chunks
    assert elapsed < 10.0, (
        f"{len(text):,} chars took {elapsed:.1f}s — sentence splitting has "
        "probably become quadratic again"
    )
