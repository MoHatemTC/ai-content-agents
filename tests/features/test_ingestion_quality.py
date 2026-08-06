"""Tests for the ingestion quality gate.

The gate decides what is worth storing, and two of its heuristics were rejecting
real study material while accepting noise. Both failures came from measuring
something adjacent to the question being asked:

* repetition was measured across the whole document, so **length** read as
  repetition and a 1,598-page textbook was refused;
* readability counted **letters** against every character, so a worked physics
  solution - legitimately a fifth digits and a fifth operators - read as
  unreadable.

The numbers in these tests are taken from the real documents that failed.
"""

from __future__ import annotations

import pytest

from src.ingestion.quality import QualityChecker


@pytest.fixture()
def checker() -> QualityChecker:
    return QualityChecker()


# A worked solution from the physics notes that a vision model transcribed.
# 24% letters, 22% digits, the rest operators and spacing.
WORKED_PHYSICS = (
    "Assignment (Mechanism of heat transfer) 3. H = A (T_H - T_C) / R "
    "Where R = L / k R_wood = (0.03 x 10^-2) / 0.08 = 0.375 "
    "R_styrofoam = (2.2 x 10^-2) / 0.01 = 0.275 H_wood = H_styrofoam "
    "0.375T + 3.75 = 5.295 - 0.275T 0.65T = 1.475 T = 2.27 C "
    "6. H = 150 J/s T_H = 400 T_C = 100 L = 0.5 m k = 50.2 "
    "A = 4.98 x 10^-3 m^2 6.36 r^2 + 3.18 r - 4.98 x 10^-3 = 0 "
    "r = 1.5612 x 10^-3 m D = 2r = 3.1824 x 10^-3 m"
)

PROSE = (
    "Diplomacy is the practice of negotiation between nations. Envoys carry "
    "instructions from their capitals and report what they learn abroad. "
    "Treaties record the settlements those talks produce, binding successors "
    "who never sat at the table."
)


# --------------------------------------------------------------------------- #
# Readability: is this writing, or is it characters?
# --------------------------------------------------------------------------- #


def test_worked_maths_is_readable(checker: QualityChecker) -> None:
    """Digits and operators are content. This scored 0.29 and was rejected."""
    result = checker.validate(WORKED_PHYSICS)

    assert result.passed, result.issues


def test_prose_is_readable(checker: QualityChecker) -> None:
    result = checker.validate(PROSE)

    assert result.passed, result.issues


@pytest.mark.parametrize(
    ("label", "text"),
    [
        (
            "box-drawing mojibake",
            "".join(chr(0x2580 + index % 60) for index in range(400)),
        ),
        ("control characters", "".join(chr(index % 30 + 1) for index in range(400))),
    ],
)
def test_unreadable_bytes_are_refused(
    checker: QualityChecker, label: str, text: str
) -> None:
    """What the check is actually for: characters that are not writing."""
    result = checker.validate(text)

    assert not result.passed, label
    assert "readable" in " ".join(result.issues)


def test_whitespace_does_not_count_against_readability(checker: QualityChecker) -> None:
    """Spacing is neither readable nor noise, so it must not dilute the ratio."""
    spaced = "   ".join(PROSE.split())

    assert checker.validate(spaced).passed


# --------------------------------------------------------------------------- #
# Repetition: measured per window, because vocabulary thins out with length
# --------------------------------------------------------------------------- #


def test_a_long_varied_document_is_not_called_repetitive(
    checker: QualityChecker,
) -> None:
    """The failure that started this: length must not read as repetition.

    Distinct-words-over-total-words falls as a document grows however varied its
    prose, because function words recur without limit while new words run out
    (Heaps' law). A 1,598-page physics textbook scored 0.019 against a 0.20 floor
    whole-document, and 0.381 over its first 2,000 words.
    """
    # 40,000 words with a vocabulary of 4,000 - varied, but far longer than any
    # single window, which is exactly the shape that used to fail.
    varied = " ".join(f"term{index % 4000}" for index in range(40_000))

    result = checker.validate(varied)

    assert result.passed, result.issues


def test_genuinely_repetitive_content_is_still_refused(
    checker: QualityChecker,
) -> None:
    result = checker.validate("spam eggs " * 400)

    assert not result.passed
    assert "repetitive" in " ".join(result.issues)


def test_a_short_trailing_window_cannot_rescue_repetitive_text(
    checker: QualityChecker,
) -> None:
    """A stray final window would otherwise vote 1.0 and carry the average.

    Three words are almost always three distinct words, so a document just over
    one window long would average a near-zero window with a perfect one and pass.
    """
    just_over_one_window = "spam " * (QualityChecker.REPETITION_WINDOW_WORDS + 1)

    result = checker.validate(just_over_one_window)

    assert not result.passed
    assert "repetitive" in " ".join(result.issues)


# --------------------------------------------------------------------------- #
# The checks that were already right
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ["", "   \n  ", None])
def test_empty_documents_are_refused(checker: QualityChecker, text) -> None:
    result = checker.validate(text)

    assert not result.passed
    assert result.score == 0.0


def test_short_documents_are_refused(checker: QualityChecker) -> None:
    result = checker.validate("Too short to be useful.")

    assert not result.passed
    assert "too short" in " ".join(result.issues).lower()
