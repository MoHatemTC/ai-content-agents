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
        return False, "the pytesseract package is not installed (pip install pytesseract)"

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
        for number, page in enumerate(document, start=1):
            # Round-trip through PNG rather than reading pix.samples directly:
            # it sidesteps having to handle colourspace and alpha variations.
            image = Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png")))
            text = pytesseract.image_to_string(image, lang=language)
            logger.info("ocr page %d/%d: %d chars", number, len(document), len(text))
            pages.append(text)
    finally:
        document.close()

    return "\n".join(pages)


class OcrUnavailableError(RuntimeError):
    """Raised when OCR is requested but cannot run on this machine."""
