"""Tests for structural query routing (chapter / section references).

Dense retrieval cannot serve "explain chapter 4": the query carries no topical
signal, so the nearest neighbours are wherever the *string* "Chapter 4" is
densest - the table of contents, the preface, the answer key. That is what the
live app returned, and docs/agent-parity.md recorded it as a known refusal.

These tests pin the two pieces that close it: reading a structural reference out
of a query, and confining retrieval to the ordinals that reference covers.
"""

from __future__ import annotations

import pytest

from src.retrieval.models import RetrievalScope
from src.retrieval.structure import (
    STRUCTURE_BACK_MATTER,
    STRUCTURE_FRONT_MATTER,
    StructureRef,
    label_sections,
    parse_structure_ref,
)


# --------------------------------------------------------------------------- #
# Query parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("explain chapter 4", StructureRef(kind="chapter", number="4")),
        ("Chapter 4", StructureRef(kind="chapter", number="4")),
        ("what is in ch. 3?", StructureRef(kind="chapter", number="3")),
        ("ch 12 summary", StructureRef(kind="chapter", number="12")),
        ("summarise section 2.6", StructureRef(kind="section", number="2.6")),
        ("Section 10.1", StructureRef(kind="section", number="10.1")),
        # A bare "2.6" is a section reference too - it is how a textbook is cited.
        ("explain 2.6", StructureRef(kind="section", number="2.6")),
    ],
)
def test_parses_structural_references(query: str, expected: StructureRef) -> None:
    assert parse_structure_ref(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "what is a vector space",
        "explain the Leontief input-output model",
        "",
        # Topical queries that merely contain a digit must not be hijacked:
        # confining these to one chapter would be worse than not routing at all.
        "what does R^3 mean",
        "solve for x in 3 dimensions",
    ],
)
def test_topical_queries_are_not_structural(query: str) -> None:
    assert parse_structure_ref(query) is None


# --------------------------------------------------------------------------- #
# Section labelling
# --------------------------------------------------------------------------- #


def test_labels_chapters_and_carries_them_forward() -> None:
    """Every chunk inherits the last heading seen above it."""
    texts = [
        "Front cover, table of contents, preface material.",
        "CHAPTER 1 Linear Equations. A system of linear equations is...",
        "continuing the discussion of row reduction and echelon forms",
        "CHAPTER 2 Matrix Algebra. Matrix operations are defined as...",
        "2.6 The Leontief Input-Output Model. Suppose a nation's economy...",
        "continuing the Leontief discussion with the production vector",
    ]

    labels = label_sections(texts)

    assert labels[0] == STRUCTURE_FRONT_MATTER
    assert labels[1] == "1"
    assert labels[2] == "1"  # carried forward, no heading of its own
    assert labels[3] == "2"
    assert labels[4] == "2.6"
    assert labels[5] == "2.6"


def test_back_matter_is_flagged() -> None:
    texts = [
        "CHAPTER 1 Linear Equations.",
        "row reduction and echelon forms, continued",
        "CHAPTER 2 Matrix Algebra.",
        "matrix operations, continued",
        "Answers to Odd-Numbered Exercises",
        "1. x = 3   3. x = -1   5. no solution",
    ]

    labels = label_sections(texts)

    assert labels[0] == "1"
    assert labels[3] == "2"
    assert labels[4] == STRUCTURE_BACK_MATTER
    assert labels[5] == STRUCTURE_BACK_MATTER


def test_contents_page_listing_the_answer_key_is_not_back_matter() -> None:
    """The regression that mislabelled 853 of a textbook's 861 chunks.

    A contents page lists "Answers to Odd-Numbered Exercises" as a line item
    before any chapter has started. Latching there swallowed the entire book.
    """
    texts = [
        "Answers to Odd-Numbered Exercises A17 Index I1 Photo Credits P1 Preface",
        "CHAPTER 1 Linear Equations.",
        "a system of linear equations is a collection of one or more equations",
        "CHAPTER 2 Matrix Algebra.",
    ]

    labels = label_sections(texts)

    assert labels[0] == STRUCTURE_FRONT_MATTER
    assert labels[1] == "1"
    assert labels[2] == "1"
    assert labels[3] == "2"
    assert STRUCTURE_BACK_MATTER not in labels


def test_cross_chapter_reference_does_not_advance_the_chapter() -> None:
    """"see CHAPTER 7" inside chapter 2 must not relabel everything after it."""
    texts = [
        "CHAPTER 2 Matrix Algebra.",
        "this result is proved in CHAPTER 7 using orthogonal diagonalization",
        "matrix factorizations continued",
        "CHAPTER 3 Determinants.",
    ]

    assert label_sections(texts) == ["2", "2", "2", "3"]


def test_contents_page_section_numbers_are_not_headings() -> None:
    """A contents page lists sections from every chapter at once.

    Accepting a section only inside its own chapter is what discards them.
    """
    texts = [
        "1.1 Systems of Linear Equations 2  4.4 Coordinate Systems 216  9.3 Ax 531",
        "CHAPTER 1 Linear Equations.",
        "1.1 Systems of Linear Equations. A linear equation in the variables",
    ]

    labels = label_sections(texts)

    assert labels[0] == STRUCTURE_FRONT_MATTER
    assert labels[2] == "1.1"


def test_document_without_headings_is_left_unlabelled() -> None:
    """No headings detected means no claim made - today's behaviour, exactly.

    A lecture handout or a scanned page set has no CHAPTER lines. Guessing a
    structure for it would confine retrieval to a range that means nothing.
    """
    texts = [
        "Mitochondria are the organelles that produce most of the cell's ATP.",
        "Photosynthesis converts light energy into chemical energy.",
    ]

    assert label_sections(texts) == [None, None]


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def test_scope_without_ordinal_range_is_unchanged() -> None:
    scope = RetrievalScope(document_id="doc-1")
    assert scope.to_where() == {"document_id": "doc-1"}


def test_ordinal_range_confines_the_search() -> None:
    scope = RetrievalScope(document_id="doc-1", ordinal_range=(120, 180))

    assert scope.to_where() == {
        "$and": [
            {"document_id": "doc-1"},
            {"ordinal": {"$gte": 120, "$lte": 180}},
        ]
    }


def test_ordinal_range_composes_with_session_scope() -> None:
    scope = RetrievalScope(
        document_id="doc-1", session_id="s-1", ordinal_range=(0, 10)
    )

    assert scope.to_where() == {
        "$and": [
            {"document_id": "doc-1"},
            {"session_id": "s-1"},
            {"ordinal": {"$gte": 0, "$lte": 10}},
        ]
    }


def test_ordinal_range_alone_is_still_an_unscoped_retrieval() -> None:
    """A range is a filter within a scope, not a scope of its own."""
    with pytest.raises(ValueError, match="unscoped retrieval is not allowed"):
        RetrievalScope(ordinal_range=(0, 10))
