"""Maths that did not survive PDF extraction is marked, not guessed at.

A textbook typesets maths in symbol fonts whose glyph codes are not Unicode, so
the extractor emits the raw code. Measured on Linear Algebra and Its
Applications: **781 of 861 chunks affected (91%), 21,199 characters**, with
0x00 alone appearing 9,920 times::

    '... the only solution of the original system is (1, 0, \x021) ...'

That \x02 is almost certainly a minus. Nothing in the lane handled these, so
they reached the index and the prompt untouched, and the model had to guess.

Stripping them would be worse than leaving them: '(1, 0, \x021)' becomes
'(1, 0, 1)', a sign flip presented as fact. Mapping them to symbols is
font-dependent guesswork - in this document 0x15 appears both as a relation and
as a Greek letter. So the gap is marked and the prompts are told to report it.
"""

from __future__ import annotations

import yaml
import pytest
from pathlib import Path

from src.ingestion.cleaner import UNREADABLE_MARKER, TextCleaner

PROMPTS = Path(__file__).resolve().parents[2] / "src" / "prompts"
CONTENT_PROMPTS = ["mentor.yaml", "concept.yaml", "question_bank.yaml", "test_help.yaml"]


# --------------------------------------------------------------------------- #
# The cleaner marks the gap
# --------------------------------------------------------------------------- #


def test_a_lost_symbol_becomes_a_visible_marker() -> None:
    """The exact shape seen in the textbook."""
    cleaned = TextCleaner.clean("the solution is (1, 0, \x021)")

    assert cleaned == f"the solution is (1, 0, {UNREADABLE_MARKER}1)"


def test_the_marker_is_not_silently_dropped() -> None:
    """Stripping would turn a minus into its opposite and call it fact."""
    cleaned = TextCleaner.clean("x = \x021")

    assert "1" in cleaned
    assert cleaned != "x = 1", "a sign was silently deleted"
    assert UNREADABLE_MARKER in cleaned


@pytest.mark.parametrize("code", ["\x00", "\x01", "\x02", "\x15", "\x14", "\x7f"])
def test_every_code_seen_in_the_corpus_is_marked(code: str) -> None:
    assert UNREADABLE_MARKER in TextCleaner.clean(f"a{code}b")


def test_a_run_of_them_collapses_to_one_marker() -> None:
    """Three lost glyphs in a row are one unreadable region, not three."""
    assert TextCleaner.clean("a\x00\x01\x02b") == f"a{UNREADABLE_MARKER}b"


def test_whitespace_behaviour_is_unchanged() -> None:
    """The established contract test_text_cleaner pins. Tabs and newlines are
    whitespace and must keep collapsing, not turn into markers."""
    assert TextCleaner.clean("  a\t\tb\n\nc  ") == "a b c"
    assert UNREADABLE_MARKER not in TextCleaner.clean("a\tb\nc\r\nd")


def test_ordinary_text_is_untouched() -> None:
    assert TextCleaner.clean("Vector spaces are closed under addition.") == (
        "Vector spaces are closed under addition."
    )


# --------------------------------------------------------------------------- #
# The prompts report the gap rather than filling it
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("filename", CONTENT_PROMPTS)
def test_the_prompt_asks_for_latex(filename: str) -> None:
    """Streamlit renders $...$; the prompts simply never asked for it."""
    data = yaml.safe_load((PROMPTS / filename).read_text(encoding="utf-8"))
    everything = " ".join(data["instructions"]) + data["prompt_template"]

    assert "LaTeX" in everything
    assert "$...$" in everything


@pytest.mark.parametrize("filename", CONTENT_PROMPTS)
def test_the_prompt_forbids_reconstructing_a_lost_symbol(filename: str) -> None:
    """The half that matters.

    Without it, LaTeX is a prettier way to be wrong: a guessed minus sign
    typeset beautifully is more convincing than the raw control character it
    replaced - the same failure #38 found with citations.
    """
    data = yaml.safe_load((PROMPTS / filename).read_text(encoding="utf-8"))
    template = data["prompt_template"]

    assert UNREADABLE_MARKER in template
    assert "never reconstruct" in template.lower() or "do not guess" in template.lower()


@pytest.mark.parametrize("filename", CONTENT_PROMPTS)
def test_the_prompt_keeps_its_shape(filename: str) -> None:
    data = yaml.safe_load((PROMPTS / filename).read_text(encoding="utf-8"))

    assert list(data) == [
        "name",
        "description",
        "role",
        "instructions",
        "output_schema",
        "notes",
        "prompt_template",
    ]
