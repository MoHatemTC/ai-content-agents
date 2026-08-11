"""Optional OCR fallback for PDFs that carry no text layer.

A scanned or photographed PDF stores pages as images, so ``page.get_text()``
returns nothing and ingestion rejects the document as empty. OCR is the only way
to read those: render each page to an image and recognise the characters.

**This depends on a system binary, not just a Python package.** ``pytesseract``
is a thin wrapper around the Tesseract executable, which has to be installed
separately on every machine that runs ingestion:

* Windows: https://github.com/UB-Mannheim/tesseract/wiki
* macOS: ``brew install tesseract``
* Debian/Ubuntu: ``apt-get install tesseract-ocr``

Because that cannot be assumed, nothing here is mandatory. OCR runs only when
``ENABLE_OCR=true`` **and** the binary is actually present; otherwise
:func:`ocr_availability` explains precisely what is missing so the caller can
tell the user something useful instead of "Document is empty".

It is also slow — seconds per page against milliseconds for normal extraction —
which is why it is a fallback for documents that yielded nothing, never the
default path.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# The ingestion lane is importable on its own - `streamlit run src/ingestion/ui.py`
# loads none of the agent modules that happen to call this elsewhere - so without
# it here, ENABLE_OCR in .env would be honoured by the combined app and silently
# ignored by the standalone upload page.
load_dotenv()

INSTALL_HINT = (
    "Install the Tesseract binary to enable OCR: "
    "Windows https://github.com/UB-Mannheim/tesseract/wiki, "
    "macOS 'brew install tesseract', "
    "Linux 'apt-get install tesseract-ocr'."
)

# Where the standard Windows installers put tesseract.exe. Both the UB-Mannheim
# installer and `choco install tesseract` land here, and both leave it off the
# PATH of any process that was already running - and off the machine PATH
# entirely, so a service started from an old environment never sees it. Checking
# these means an install that plainly succeeded is not reported as missing.
_WINDOWS_FALLBACK_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def ocr_enabled() -> bool:
    """Return whether OCR is switched on for this process.

    Read from the environment on every call rather than at import time, so a
    deployment (or a test) can change it without reimporting the module.

    Returns:
        ``True`` when ``ENABLE_OCR`` is set to a truthy value.
    """
    return os.getenv("ENABLE_OCR", "false").strip().lower() in {"1", "true", "yes"}


def find_tesseract() -> str | None:
    """Locate the Tesseract binary, PATH first then the known install locations.

    Returns:
        The path to the executable, or ``None`` when it cannot be found.
    """
    configured = os.getenv("TESSERACT_CMD")
    if configured and Path(configured).is_file():
        return configured

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    for candidate in _WINDOWS_FALLBACK_PATHS:
        if candidate.is_file():
            logger.info("tesseract found off PATH at %s", candidate)
            return str(candidate)

    return None


def ocr_availability() -> tuple[bool, str]:
    """Report whether OCR can actually run, and why not when it cannot.

    Distinguishes the two failure modes that need different fixes: the Python
    wrapper missing (a ``pip install``) versus the Tesseract binary missing (a
    system install).

    Returns:
        ``(available, reason)``. ``reason`` is empty when available, otherwise a
        sentence naming what to do about it.
    """
    try:
        import pytesseract
    except ImportError:
        return (
            False,
            "the pytesseract package is not installed (pip install pytesseract)",
        )

    binary = find_tesseract()
    if binary is None:
        return False, f"the Tesseract binary was not found. {INSTALL_HINT}"

    # pytesseract shells out to whatever this points at; it defaults to bare
    # "tesseract", which only resolves via PATH.
    pytesseract.pytesseract.tesseract_cmd = binary

    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 - any failure means unusable
        logger.info("tesseract unusable at %s: %s", binary, exc)
        return False, f"the Tesseract binary at {binary} could not be run ({exc})."

    return True, ""


# Artefacts every page of a phone-scanned document carries: the scanner app's
# watermark and the printed template fields of the notebook itself. They repeat
# on every page, so they dominate word frequencies and get mistaken for the
# document's subject matter - a scan of physics notes produced flashcards titled
# "CamScanner", "PAGE" and "DATE".
_FURNITURE_PATTERNS = (
    r"scanned\s+with\s+camscanner",
    r"\bcamscanner\b",
    r"\bscanned\s+by\s+\w+",
    r"\bkwad\s+res\b",
    r"^\s*page\s*(no\.?|number)?\s*:?\s*\d*\s*$",
    r"^\s*date\s*:?\s*$",
    r"\bpage\s+date\b",
)
_FURNITURE = re.compile("|".join(_FURNITURE_PATTERNS), re.IGNORECASE | re.MULTILINE)

# A minimal common-English vocabulary, used only to ask whether OCR produced
# words at all. Deliberately not a full dictionary: the question is "is this
# language or is it noise", and noise scores zero against any word list.
_COMMON_WORDS = frozenset(
    [
        "the",
        "be",
        "to",
        "of",
        "and",
        "a",
        "in",
        "that",
        "have",
        "it",
        "for",
        "not",
        "on",
        "with",
        "he",
        "as",
        "you",
        "do",
        "at",
        "this",
        "but",
        "his",
        "by",
        "from",
        "they",
        "we",
        "say",
        "her",
        "she",
        "or",
        "an",
        "will",
        "my",
        "one",
        "all",
        "would",
        "there",
        "their",
        "what",
        "so",
        "up",
        "out",
        "if",
        "about",
        "who",
        "get",
        "which",
        "go",
        "me",
        "when",
        "make",
        "can",
        "like",
        "time",
        "no",
        "just",
        "him",
        "know",
        "take",
        "people",
        "into",
        "year",
        "your",
        "good",
        "some",
        "could",
        "them",
        "see",
        "other",
        "than",
        "then",
        "now",
        "look",
        "only",
        "come",
        "its",
        "over",
        "think",
        "also",
        "back",
        "after",
        "use",
        "two",
        "how",
        "our",
        "work",
        "first",
        "well",
        "way",
        "even",
        "new",
        "want",
        "because",
        "any",
        "these",
        "give",
        "day",
        "most",
        "us",
        "is",
        "are",
        "was",
        "were",
        "been",
        "has",
        "had",
        "did",
        "does",
        "said",
        "made",
        "where",
        "much",
        "before",
        "through",
        "between",
        "under",
        "both",
        "each",
        "many",
        "such",
        "own",
        "same",
        "those",
        "while",
        "during",
        "against",
        "per",
        "via",
        "value",
        "values",
        "result",
        "results",
        "example",
        "examples",
        "figure",
        "table",
        "chapter",
        "section",
        "problem",
        "problems",
        "equation",
        "equations",
        "force",
        "energy",
        "mass",
        "velocity",
        "motion",
        "system",
        "point",
        "line",
        "surface",
        "field",
        "temperature",
        "heat",
        "water",
        "object",
        "body",
        "speed",
        "direction",
        "distance",
        "change",
        "rate",
        "constant",
    ]
)

# Below this share of recognisable words, the text is noise rather than content.
# Measured on the real failure: a scanned page of handwritten physics scored
# 0.000 once its scanner furniture was removed, while the weakest legitimate
# document in this repo scores 0.14 and a vision transcription of the same page
# scores 0.57.
MIN_LEXICALITY = 0.08

# Mean per-word confidence below which Tesseract is guessing. The same page
# scored 41.1; a clean printed scan sits comfortably above 70.
MIN_MEAN_CONFIDENCE = 55.0


def strip_scanner_furniture(text: str) -> str:
    """Remove scanner watermarks and notebook template text from OCR output.

    Args:
        text: Raw OCR output.

    Returns:
        The same text without the per-page artefacts, whitespace tidied.
    """
    return re.sub(r"[ \t]{2,}", " ", _FURNITURE.sub(" ", text)).strip()


def lexicality(text: str) -> float:
    """Return the share of word-like tokens that are recognisable English words.

    This is the signal that separates a real transcription from OCR noise, and
    it is applied **only** to OCR output. Ordinary uploaded documents are not
    judged this way: technical, non-English or heavily notated prose can score
    low without being wrong, and there is no reason to gamble a user's upload on
    a word list.

    Args:
        text: Text to score, ideally with scanner furniture already stripped -
            the watermark words are real English and inflate the score.

    Returns:
        A ratio in ``[0.0, 1.0]``; ``0.0`` when there are no word-like tokens.
    """
    tokens = [
        token for token in re.findall(r"[A-Za-z]+", text.lower()) if len(token) > 2
    ]
    if not tokens:
        return 0.0
    return sum(token in _COMMON_WORDS for token in tokens) / len(tokens)


def ocr_pdf(file_content: bytes, *, dpi: int = 300, language: str = "eng") -> str:
    """Extract text from a PDF by rendering each page and running OCR on it.

    Args:
        file_content: Raw PDF bytes.
        dpi: Render resolution. 300 is the usual floor for reliable recognition;
            lower is faster but loses small text.
        language: Tesseract language code(s), e.g. ``"eng"`` or ``"eng+ara"``.

    Returns:
        The recognised text, pages joined by newlines. May be empty if the pages
        genuinely contain no readable characters.

    Raises:
        OcrUnavailableError: If OCR cannot run on this machine.
    """
    available, reason = ocr_availability()
    if not available:
        raise OcrUnavailableError(f"OCR is not available: {reason}")

    import fitz
    import pytesseract
    from PIL import Image

    document = fitz.open(stream=file_content, filetype="pdf")
    try:
        pages: list[str] = []
        confidences: list[float] = []
        for number, page in enumerate(document, start=1):
            # Round-trip through PNG rather than reading pix.samples directly:
            # it sidesteps having to handle colourspace and alpha variations.
            image = Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png")))
            data = pytesseract.image_to_data(
                image, lang=language, output_type=pytesseract.Output.DICT
            )
            words = [
                (word.strip(), float(conf))
                for word, conf in zip(data["text"], data["conf"])
                if word.strip() and float(conf) >= 0
            ]
            text = " ".join(word for word, _ in words)
            confidences.extend(conf for _, conf in words)
            logger.info(
                "ocr page %d/%d: %d chars, %d words",
                number,
                len(document),
                len(text),
                len(words),
            )
            pages.append(text)
    finally:
        document.close()

    _LAST_MEAN_CONFIDENCE.append(
        sum(confidences) / len(confidences) if confidences else 0.0
    )
    return "\n".join(pages)


# Confidence is produced as a side effect of the pass that builds the text; a
# second OCR pass purely to measure it would double the slowest step in
# ingestion. Only the most recent value is kept.
_LAST_MEAN_CONFIDENCE: list[float] = []


def last_mean_confidence() -> float:
    """Return the mean per-word confidence of the most recent :func:`ocr_pdf` call.

    Returns:
        The mean confidence in ``[0, 100]``, or ``0.0`` if OCR has not run.
    """
    return _LAST_MEAN_CONFIDENCE[-1] if _LAST_MEAN_CONFIDENCE else 0.0


def ocr_looks_readable(
    text: str, mean_confidence: float | None = None
) -> tuple[bool, str]:
    """Judge whether OCR actually read the document, or merely produced characters.

    Tesseract recognises printed text; it cannot read handwriting, and on a
    handwritten page it does not fail - it returns confident-looking nonsense.
    Worse, the only words it gets right there are the *printed* ones, so
    filtering by confidence keeps the scanner watermark and discards everything
    else. Judging the text as a whole is the way to catch this.

    Args:
        text: OCR output, with scanner furniture already stripped.
        mean_confidence: Mean per-word confidence, if known. Defaults to the most
            recent :func:`ocr_pdf` run.

    Returns:
        ``(readable, reason)``. ``reason`` is empty when the text looks like
        language, otherwise it names what was wrong.
    """
    confidence = last_mean_confidence() if mean_confidence is None else mean_confidence
    score = lexicality(text)

    if score < MIN_LEXICALITY:
        return False, (
            f"the recognised text is not readable language ({score:.0%} of words "
            f"recognisable, mean confidence {confidence:.0f}/100). The page is "
            "most likely handwritten - Tesseract reads printed text only."
        )

    if confidence and confidence < MIN_MEAN_CONFIDENCE:
        return False, (
            f"OCR confidence was too low to trust ({confidence:.0f}/100). The scan "
            "may be blurred, skewed, or too low-resolution."
        )

    return True, ""


class OcrUnavailableError(RuntimeError):
    """Raised when OCR is requested but cannot run on this machine."""
