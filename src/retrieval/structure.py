"""Structural references: reading them from a query, labelling them in a document.

Dense retrieval answers "what is a vector space" well and "explain chapter 4"
not at all. The second query carries no topical signal — nothing in the phrase
resembles the chapter's content — so cosine similarity lands on the pages where
the literal string "Chapter 4" is densest: the table of contents, the preface,
and the answer key. The live app did exactly that, reporting back that the
material "covers portions of the preface, answers to odd-numbered exercises".
``docs/agent-parity.md`` recorded it as a refusal the agents were right to make,
because chunks carried no chapter metadata to serve it with.

This module supplies that metadata. :func:`label_sections` walks a document's
chunks in order and gives each one the heading it falls under; the labels go in
the ``document_chunks.section`` column, which has existed since M3 and was never
populated. :func:`parse_structure_ref` reads a reference back out of a query so
retrieval can be confined to the matching ordinals.

**The labelling is deliberately conservative.** Heading shapes vary by
publisher, and a wrong structure is worse than none: it would confine retrieval
to a range that means nothing. When no headings are found, every label is
``None`` and retrieval behaves exactly as it does today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Chunks before the first chapter heading — title page, table of contents,
#: preface. They match "chapter N" queries lexically while containing none of
#: the chapter's actual material.
STRUCTURE_FRONT_MATTER = "front-matter"

#: Chunks from the answer key onward. Same problem: dense with section numbers,
#: empty of explanation.
STRUCTURE_BACK_MATTER = "back-matter"

# "CHAPTER 4" — in a typeset textbook this is the running page header, repeated
# on every page of the chapter, so it appears *within* a chunk rather than at
# its start. That repetition is what makes it trustworthy: one missed heading
# costs nothing when the next page carries it again. Upper case only; "chapter"
# in running prose is a mention, not a header.
_CHAPTER_HEADER = re.compile(r"\bCHAPTER\s+(\d{1,2})\b")

# "2.6 The Leontief Input-Output Model" — a numbered section followed by its
# title. Accepted only inside its own chapter (see below), which is what keeps
# the table of contents and cross-references from being read as headings.
_SECTION_HEADER = re.compile(r"\b(\d{1,2})\.(\d{1,2})\s+[A-Z][a-z]")

# The answer key and what follows it. The cleaner collapses whitespace, so a
# chunk has no line structure to anchor to and this has to match anywhere in
# the text. Two guards keep that from firing early, because the latch is
# permanent: a chapter must already have been seen, and the chunk must be in
# the second half of the document. The contents page lists these same titles,
# and latching there labelled 853 of a textbook's 861 chunks as back matter.
_BACK_MATTER_HEADING = re.compile(
    r"(answers?\s+to\s+odd[-\s]numbered\s+exercises"
    r"|answers?\s+to\s+exercises)",
    re.IGNORECASE,
)

#: How far into a document the answer key may first appear.
_BACK_MATTER_EARLIEST = 0.5

# Query-side forms. "ch" needs the boundary or it fires on "chemistry".
_QUERY_SECTION = re.compile(
    r"\bsection\s+(\d{1,2}\.\d{1,2})\b", re.IGNORECASE
)
_QUERY_CHAPTER = re.compile(
    r"\b(?:chapter|ch\.|ch)\s+(\d{1,2})\b", re.IGNORECASE
)
# A bare "2.6" is how a textbook section is cited in conversation. Anchored to
# a decimal pair so it cannot catch "R^3" or "3 dimensions".
_QUERY_BARE_SECTION = re.compile(r"(?<![\w.])(\d{1,2}\.\d{1,2})(?![\w.])")


@dataclass(frozen=True)
class StructureRef:
    """A chapter or section a query is asking about.

    Attributes:
        kind: ``"chapter"`` or ``"section"``.
        number: ``"4"`` for a chapter, ``"2.6"`` for a section — the same
            string shape :func:`label_sections` writes to ``section``.
    """

    kind: str
    number: str

    def matches(self, label: str | None) -> bool:
        """Whether a chunk's ``section`` label falls under this reference.

        A chapter reference covers its own sections: "chapter 2" includes
        ``"2"``, ``"2.6"`` and ``"2.10"``, but not ``"20"`` or ``"12"``.
        """
        if not label or label in (STRUCTURE_FRONT_MATTER, STRUCTURE_BACK_MATTER):
            return False
        if self.kind == "section":
            return label == self.number
        return label == self.number or label.startswith(f"{self.number}.")


def parse_structure_ref(query: str) -> StructureRef | None:
    """Read a chapter/section reference out of a query.

    Args:
        query: The user's question, as typed.

    Returns:
        The reference, or ``None`` when the query is topical. Returning
        ``None`` is the common case and must stay cheap to be wrong about:
        an unrouted query simply retrieves the way it always has.
    """
    if not query:
        return None

    section = _QUERY_SECTION.search(query)
    if section:
        return StructureRef(kind="section", number=section.group(1))

    chapter = _QUERY_CHAPTER.search(query)
    if chapter:
        return StructureRef(kind="chapter", number=chapter.group(1))

    bare = _QUERY_BARE_SECTION.search(query)
    if bare:
        return StructureRef(kind="section", number=bare.group(1))

    return None


def label_sections(texts: list[str]) -> list[str | None]:
    """Label each chunk with the heading it falls under.

    Walks the chunks in document order, carrying the last heading forward so a
    chunk in the middle of a section still knows which section it is in.

    Args:
        texts: Chunk texts, in document order.

    Returns:
        One label per chunk: a chapter (``"2"``), a section (``"2.6"``),
        :data:`STRUCTURE_FRONT_MATTER`, :data:`STRUCTURE_BACK_MATTER`, or
        ``None`` for every chunk when the document has no detectable headings.
    """
    labels: list[str | None] = []
    current: str | None = STRUCTURE_FRONT_MATTER
    chapter_no = 0  # 0 = still in front matter
    in_back_matter = False

    back_matter_floor = len(texts) * _BACK_MATTER_EARLIEST

    for index, text in enumerate(texts):
        if (
            not in_back_matter
            and chapter_no
            and index >= back_matter_floor
            and _BACK_MATTER_HEADING.search(text)
        ):
            in_back_matter = True

        if in_back_matter:
            labels.append(STRUCTURE_BACK_MATTER)
            continue

        chapter = _CHAPTER_HEADER.search(text)
        if chapter:
            found = int(chapter.group(1))
            # The first chapter seen sets the baseline — an uploaded excerpt
            # can legitimately open at chapter 5. After that chapters advance
            # by one and never jump: "see CHAPTER 7" inside chapter 2 is a
            # cross-reference, and following it would mislabel the rest.
            if chapter_no == 0 or found in (chapter_no, chapter_no + 1):
                chapter_no = found
                current = str(found)

        if chapter_no:
            section = _SECTION_HEADER.search(text)
            # A section only counts inside its own chapter. That single check
            # discards the contents page (which lists 1.1, 4.4, 9.3 together
            # before any chapter has started) and cross-chapter references.
            if section and int(section.group(1)) == chapter_no:
                current = f"{section.group(1)}.{section.group(2)}"

        labels.append(current)

    # No chapter was ever found: make no claim about this document's structure.
    if not chapter_no:
        return [None] * len(texts)
    return labels


def ordinal_range_for(
    labels: list[str | None], ref: StructureRef
) -> tuple[int, int] | None:
    """Find the ordinal span covered by a structural reference.

    Args:
        labels: Chunk labels in ordinal order, as :func:`label_sections` returns.
        ref: The reference to locate.

    Returns:
        An inclusive ``(first, last)`` ordinal pair, or ``None`` when the
        reference matches nothing — in which case the caller retrieves
        unconfined rather than returning an empty result.
    """
    matching = [i for i, label in enumerate(labels) if ref.matches(label)]
    if not matching:
        return None
    return matching[0], matching[-1]
