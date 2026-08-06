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
    lexicality,
    ocr_availability,
    ocr_enabled,
    ocr_looks_readable,
    ocr_pdf,
    strip_scanner_furniture,
)
from src.ingestion.vision_ocr import transcribe_pdf, vision_ocr_enabled

# The real thing: what Tesseract returned for a scanned page of handwritten
# physics notes. It ingested cleanly and became flashcards titled "CamScanner",
# "PAGE" and "DATE". Every test about recognising noise is measured against this
# rather than an invented string, because an invented one is easy to catch.
REAL_OCR_NOISE = (
    "0,08 \\ A sDiyafecn � 2,2xl0- 2 0, dtd ( ra) jo! iia igi a a yal - Te} "
    "Ta -Te) Kwad Res r � | \\J-Te - [+h : ets 0/3799, TS Scanned with "
    "CamScanner PAGE DATE Na. itomyiebieieeniigainaleahageaminiileibinasieaion "
    "isteameasices ge � 2-H al Sox �Tr= 400� =~ KA Tn - Te =o� "
    "L Y 2 : 4joo- joo � k. So y) 0; 9d -3 2 Scanned with CamScanner"
)

# What a vision model returned for the same page.
REAL_VISION_TRANSCRIPTION = (
    "Assignment (Mechanism of heat transfer)\n"
    "3. H = A(T_h - T_c) / R  where R = L / k\n"
    "R_wood = (0.03 x 10^-2) / 0.08 = 0.375\n"
    "R_styrofoam = (2.2 x 10^-2) / 0.01 = 0.275\n"
    "The rate of heat flow through the wood equals the rate through the "
    "styrofoam, so we can solve for the temperature at the surface between them."
)


class _FakeVisionClient:
    """Stands in for the gateway so no test ever makes a network call."""

    def __init__(self, reply: str = REAL_VISION_TRANSCRIPTION) -> None:
        self.reply = reply
        self.calls: list[dict] = []
        self.chat = self  # client.chat.completions.create(...)
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("M", (), {"content": self.reply})
        choice = type("C", (), {"message": message})
        return type("R", (), {"choices": [choice]})


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
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("", False),
        ("no", False),
    ],
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
    monkeypatch.setenv("ENABLE_VISION_OCR", "false")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: "   \n  ")

    with pytest.raises(ValueError) as excinfo:
        loader.load_file(_scanned_pdf(), "scan.pdf")

    message = str(excinfo.value)
    assert "recognised no text at all" in message
    assert "Document is empty" not in message
    # The user is told the remaining route, not just what failed.
    assert "ENABLE_VISION_OCR=true" in message


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


# --------------------------------------------------------------------------- #
# Telling a transcription apart from noise
# --------------------------------------------------------------------------- #


def test_scanner_furniture_is_stripped() -> None:
    """The watermark and template fields repeat per page and swamp the content.

    Left in, they are the most frequent words in the document, so topic
    extraction picks them and the flashcards are about the scanner app.
    """
    stripped = strip_scanner_furniture(REAL_OCR_NOISE)

    assert "CamScanner" not in stripped
    assert "Kwad Res" not in stripped
    assert "PAGE DATE" not in stripped


def test_stripping_furniture_lowers_lexicality_to_zero() -> None:
    """The furniture is real English, so it props up the score that judges noise.

    This is why stripping has to happen before the text is assessed, not after.
    """
    assert lexicality(REAL_OCR_NOISE) > 0.0
    assert lexicality(strip_scanner_furniture(REAL_OCR_NOISE)) == 0.0


def test_real_ocr_noise_is_rejected() -> None:
    """The exact output that became flashcards about CamScanner must not pass."""
    readable, why = ocr_looks_readable(
        strip_scanner_furniture(REAL_OCR_NOISE), mean_confidence=43.9
    )

    assert readable is False
    assert "handwritten" in why


def test_real_vision_transcription_is_accepted() -> None:
    """The same page, read properly, must pass the same gate."""
    readable, why = ocr_looks_readable(REAL_VISION_TRANSCRIPTION, mean_confidence=90.0)

    assert readable is True, why


def test_low_confidence_is_rejected_even_when_the_words_are_real() -> None:
    """A blurred scan of printed text produces plausible words it did not see."""
    readable, why = ocr_looks_readable(REAL_VISION_TRANSCRIPTION, mean_confidence=20.0)

    assert readable is False
    assert "confidence" in why


# --------------------------------------------------------------------------- #
# Escalation to a vision model
# --------------------------------------------------------------------------- #


def test_vision_ocr_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """It costs money per page and produces model output, so it must be opt-in."""
    monkeypatch.delenv("ENABLE_VISION_OCR", raising=False)

    assert vision_ocr_enabled() is False


def test_unreadable_ocr_escalates_to_vision(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Noise must not be stored; the page is transcribed instead."""
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("ENABLE_VISION_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: REAL_OCR_NOISE)
    monkeypatch.setattr("src.ingestion.ocr.last_mean_confidence", lambda: 43.9)

    fake = _FakeVisionClient()
    monkeypatch.setattr("src.ingestion.vision_ocr._build_client", lambda: fake)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://gateway.invalid")
    monkeypatch.setenv("LITELLM_API_KEY", "not-a-real-key")

    document = loader.load_file(_scanned_pdf(pages=1), "notes.pdf")

    assert "CamScanner" not in document.content
    assert "heat transfer" in document.content.lower()
    assert fake.calls, "the vision model was never called"


def test_transcribed_documents_are_marked_as_such(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transcription is a reconstruction, not evidence a human supplied.

    Everywhere else in this project a citation points at text someone uploaded.
    A reviewer has to be able to tell which kind of source they are looking at,
    so the provenance travels with the document.
    """
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("ENABLE_VISION_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: REAL_OCR_NOISE)
    monkeypatch.setattr("src.ingestion.ocr.last_mean_confidence", lambda: 43.9)
    monkeypatch.setattr(
        "src.ingestion.vision_ocr._build_client", lambda: _FakeVisionClient()
    )
    monkeypatch.setenv("LITELLM_BASE_URL", "http://gateway.invalid")
    monkeypatch.setenv("LITELLM_API_KEY", "not-a-real-key")

    document = loader.load_file(_scanned_pdf(pages=1), "notes.pdf")

    assert document.source_type == "file-vision-ocr"


def test_readable_ocr_is_marked_as_ocr_not_vision(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A printed scan Tesseract read correctly must not reach the vision model."""
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("ENABLE_VISION_OCR", "true")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: " ".join(_PROSE))
    monkeypatch.setattr("src.ingestion.ocr.last_mean_confidence", lambda: 92.0)

    fake = _FakeVisionClient()
    monkeypatch.setattr("src.ingestion.vision_ocr._build_client", lambda: fake)

    document = loader.load_file(_scanned_pdf(pages=1), "printed.pdf")

    assert document.source_type == "file-ocr"
    assert not fake.calls, "vision was called for a page Tesseract read fine"


def test_handwriting_refusal_is_honest_when_vision_is_off(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without vision, the user must hear the diagnosis, not receive the noise."""
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("ENABLE_VISION_OCR", "false")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: REAL_OCR_NOISE)
    monkeypatch.setattr("src.ingestion.ocr.last_mean_confidence", lambda: 43.9)

    with pytest.raises(ValueError) as excinfo:
        loader.load_file(_scanned_pdf(pages=1), "notes.pdf")

    message = str(excinfo.value)
    assert "handwritten" in message
    assert "ENABLE_VISION_OCR=true" in message
    assert "Paste Text" in message


def test_nothing_is_stored_when_recognition_fails(
    loader: ContentLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused document must leave no half-ingested record behind."""
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("ENABLE_VISION_OCR", "false")
    monkeypatch.setattr("src.ingestion.loader.ocr_availability", lambda: (True, ""))
    monkeypatch.setattr("src.ingestion.loader.ocr_pdf", lambda _: REAL_OCR_NOISE)
    monkeypatch.setattr("src.ingestion.ocr.last_mean_confidence", lambda: 43.9)

    with pytest.raises(ValueError):
        loader.load_file(_scanned_pdf(pages=1), "notes.pdf")

    assert loader.store.get_all_documents() == []


def test_vision_transcription_always_caps_max_tokens() -> None:
    """The gateway refuses a request whose requested maximum exceeds the balance.

    It rejects on the *requested* ceiling, not on what the answer would use, so
    an uncapped call fails outright with 402 however short the page is.
    """
    fake = _FakeVisionClient()

    transcribe_pdf(_scanned_pdf(pages=1), client=fake, max_tokens=800)

    assert fake.calls[0]["max_tokens"] == 800
    assert fake.calls[0]["temperature"] == 0
