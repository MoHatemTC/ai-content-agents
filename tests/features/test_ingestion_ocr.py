"""Tests for the OCR fallback on PDFs with no text layer.

A scanned PDF stores its pages as images, so normal extraction returns nothing
and ingestion used to reject it as "Document is empty" - accurate about the
symptom, useless about the cause.

OCR depends on the Tesseract *binary*, which cannot be assumed present, so the
tests are split: the wiring and every failure path are exercised everywhere with
a stubbed recogniser, while the one test that needs real Tesseract skips when it
is absent. That way CI proves the behaviour without requiring a system install.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from src.ingestion.loader import ContentLoader
from src.ingestion.ocr import (
    OcrUnavailableError,
    ocr_availability,
    ocr_enabled,
    ocr_pdf,
)


def _scanned_pdf(pages: int = 2) -> bytes:
    """A PDF with real pages but no text layer - what a scan looks like."""
    document = fitz.open()
    for _ in range(pages):
        document.new_page()
    data = document.tobytes()
    document.close()
    return data


_PROSE = (
    "Diplomacy is the practice of conducting negotiations between nations.",
    "The United Nations promotes international peace and global cooperation.",
    "Treaties formalise agreements between states and set their obligations.",
    "Ambassadors represent their governments at foreign missions abroad.",
    "Multilateral institutions coordinate responses to shared global problems.",
)


def _text_pdf() -> bytes:
    """A normal, text-bearing PDF, for the path OCR must never touch.

    Written as several varied short lines: one long line would be clipped at the
    page edge and fall under the quality checker's 100-character minimum, while
    a repeated line would trip its repetition heuristic. Neither has anything to
    do with what this file tests, so the fixture avoids both.
    """
    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(_PROSE):
        page.insert_text((72, 120 + index * 24), line, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def loader(tmp_path: Path) -> ContentLoader:
    return ContentLoader(db_path=str(tmp_path / "ingest.db"))


# --------------------------------------------------------------------------- #
# The switch
# --------------------------------------------------------------------------- #


def test_ocr_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR is slow and needs a system binary, so it must be opt-in."""
    monkeypatch.delenv("ENABLE_OCR", raising=False)

    assert ocr_enabled() is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("TRUE", True), ("1", True), ("yes", True),
     ("false", False), ("", False), ("no", False)],
)
def test_enable_ocr_parsing(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("ENABLE_OCR", value)

    assert ocr_enabled() is expected


def test_availability_explains_what_is_missing() -> None:
    """The reason must name the fix, since the two causes need different ones."""
    available, reason = ocr_availability()

    if available:
        assert reason == ""
    else:
        assert reason
        assert "pytesseract" in reason or "Tesseract binary" in reason


# --------------------------------------------------------------------------- #
# A scanned PDF, with OCR unavailable in each of its ways
# --------------------------------------------------------------------------- #


def test_scanned_pdf_with_ocr_disabled_explains_itself(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old message said "Document is empty", which sent users nowhere."""
    monkeypatch.setenv("ENABLE_OCR", "false")

    with pytest.raises(ValueError) as excinfo:
        loader.load_file(_scanned_pdf(), "scan.pdf")

    message = str(excinfo.value)
    assert "scanned or image-only" in message
    assert "ENABLE_OCR=true" in message
    assert "Paste Text" in message
    assert "Document is empty" not in message


def test_scanned_pdf_reports_a_missing_binary(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setattr(
        "src.ingestion.loader.ocr_availability",
        lambda: (False, "the Tesseract binary was not found. Install it."),
    )

    with pytest.raises(ValueError, match="Tesseract binary was not found"):
        loader.load_file(_scanned_pdf(), "scan.pdf")


def test_ocr_that_recognises_nothing_says_so(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank or unreadable scan must not resurface as "Document is empty"."""
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: "   \n  ")

    with pytest.raises(ValueError, match="OCR ran but recognised no text"):
        loader.load_file(_scanned_pdf(), "scan.pdf")


def test_ocr_unavailable_error_is_raised_by_the_module() -> None:
    """Calling ocr_pdf directly on a machine without Tesseract must be explicit."""
    available, _ = ocr_availability()
    if available:
        pytest.skip("Tesseract is installed here; the unavailable path cannot run")

    with pytest.raises(OcrUnavailableError, match="not available"):
        ocr_pdf(_scanned_pdf())


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_ocr_recovers_a_scanned_pdf(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With OCR working, a scan ingests like any other document.

    The recogniser is stubbed so this runs everywhere; the real binary is
    exercised by test_real_tesseract_reads_a_rendered_page below.
    """
    recovered = (
        "Diplomacy is the practice of conducting negotiations between nations. "
        "The United Nations promotes international peace and cooperation. "
        "Treaties formalise agreements between states and set obligations."
    )
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: recovered)

    document = loader.load_file(_scanned_pdf(), "scan.pdf")

    assert "Diplomacy" in document.content
    assert loader.store.get_chunks_by_document_id(document.id)


def test_text_pdfs_never_reach_ocr(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OCR is a fallback; a normal PDF must not pay its cost."""
    called = False

    def _explode(_: bytes) -> str:
        nonlocal called
        called = True
        return "should not happen"

    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", _explode)

    document = loader.load_file(_text_pdf(), "notes.pdf")

    assert called is False
    assert "Diplomacy" in document.content


@pytest.mark.skipif(
    not ocr_availability()[0], reason="Tesseract binary not installed on this machine"
)
def test_real_tesseract_reads_a_rendered_page() -> None:
    """End-to-end against the real binary, when the machine has it."""
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 144), "DIPLOMACY AND TREATIES", fontsize=36)
    data = document.tobytes()
    document.close()

    text = ocr_pdf(data, dpi=200)

    assert "DIPLOMACY" in text.upper()
