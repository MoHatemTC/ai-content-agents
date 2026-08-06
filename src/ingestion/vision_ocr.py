"""Transcribe pages a conventional OCR engine cannot read, using a vision model.

Tesseract recognises printed characters. It cannot read handwriting, and it does
not report that it cannot: on a handwritten page it returns nonsense with the
same interface as success. A vision model reads such pages directly, including
the equations that make handwritten study notes worth ingesting at all.

**What this produces is model output, not extracted text**, and that distinction
matters more here than in most projects. Everywhere else in this codebase a
citation points at text a human supplied; a chunk is evidence. A transcribed page
is a reconstruction, so a hallucinated line would be indistinguishable from a
real one and would then be cited as though it were source material. Documents
recovered this way are recorded with a ``vision-ocr`` source type so the
provenance travels with them, and they belong in front of a human reviewer before
anything generated from them is trusted. This module is therefore **opt-in**
(``ENABLE_VISION_OCR``) and only ever runs on pages ordinary OCR failed to read.

It also costs money per page and is slow, which is the second reason it is an
escalation rather than the default path.
"""

from __future__ import annotations

import base64
import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# A small vision model is the default deliberately. On the page this was built
# for it transcribed *more* of the working than a larger one, and the gateway is
# credit-limited - a request that does not fit the remaining balance is refused
# outright rather than truncated.
DEFAULT_MODEL = "qwen/qwen3-vl-8b-instruct"
DEFAULT_MAX_TOKENS = 1500

# 120 DPI keeps a notebook page legible to a vision model while holding the
# encoded image small; the request carries the image inline.
DEFAULT_DPI = 120

PROMPT = (
    "Transcribe the educational content of this page: the text, equations, "
    "labels and worked steps, in reading order. Ignore scanner watermarks, "
    "page-template words such as PAGE or DATE, and notebook branding. "
    "Do not explain, summarise, correct or complete the work - transcribe only "
    "what is written. Where a region is genuinely unreadable, write [illegible] "
    "rather than guessing. If the page contains no educational content, reply "
    "with nothing at all."
)


class VisionOcrUnavailableError(RuntimeError):
    """Raised when vision transcription is requested but cannot run."""


def vision_ocr_enabled() -> bool:
    """Return whether vision transcription is switched on for this process.

    Read from the environment on every call so a deployment or a test can change
    it without reimporting the module.

    Returns:
        ``True`` when ``ENABLE_VISION_OCR`` is set to a truthy value.
    """
    return os.getenv("ENABLE_VISION_OCR", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def vision_ocr_availability() -> tuple[bool, str]:
    """Report whether a vision transcription call could be made, and why not.

    Returns:
        ``(available, reason)``. ``reason`` is empty when available.
    """
    try:
        import openai  # noqa: F401
    except ImportError:
        return False, "the openai package is not installed (pip install openai)"

    if not os.getenv("LITELLM_BASE_URL") or not os.getenv("LITELLM_API_KEY"):
        return False, "LITELLM_BASE_URL and LITELLM_API_KEY are not both set in .env"

    return True, ""


def _build_client():
    """Return an OpenAI-compatible client pointed at the configured gateway."""
    from openai import OpenAI

    return OpenAI(
        base_url=os.getenv("LITELLM_BASE_URL"),
        api_key=os.getenv("LITELLM_API_KEY"),
    )


def _page_images(file_content: bytes, dpi: int) -> list[bytes]:
    """Render every page of a PDF to PNG bytes.

    Args:
        file_content: Raw PDF bytes.
        dpi: Render resolution.

    Returns:
        One PNG per page, in order.
    """
    import fitz

    document = fitz.open(stream=file_content, filetype="pdf")
    try:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in document]
    finally:
        document.close()


def transcribe_pdf(
    file_content: bytes,
    *,
    client=None,
    model: str | None = None,
    max_tokens: int | None = None,
    dpi: int = DEFAULT_DPI,
) -> str:
    """Transcribe a PDF page by page with a vision model.

    Args:
        file_content: Raw PDF bytes.
        client: An OpenAI-compatible client. Built from the environment when
            omitted; tests inject a fake so no request is ever made.
        model: Vision model id. Defaults to ``VISION_OCR_MODEL`` or
            :data:`DEFAULT_MODEL`.
        max_tokens: Per-page output cap. Always sent explicitly - the gateway
            rejects a request whose *requested* maximum exceeds the remaining
            credit, regardless of how much the answer would actually use.
        dpi: Page render resolution.

    Returns:
        The transcription, pages joined by blank lines. May be empty when the
        model found nothing to transcribe.

    Raises:
        VisionOcrUnavailableError: If no client was supplied and one cannot be
            built from the environment.
    """
    if client is None:
        available, reason = vision_ocr_availability()
        if not available:
            raise VisionOcrUnavailableError(
                f"Vision transcription is not available: {reason}"
            )
        client = _build_client()

    model = model or os.getenv("VISION_OCR_MODEL") or DEFAULT_MODEL
    if max_tokens is None:
        max_tokens = int(os.getenv("VISION_OCR_MAX_TOKENS", DEFAULT_MAX_TOKENS))

    images = _page_images(file_content, dpi)
    pages: list[str] = []

    for number, png in enumerate(images, start=1):
        encoded = base64.b64encode(png).decode()
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,  # Transcription, not composition.
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        logger.info(
            "vision ocr page %d/%d: model=%s %d chars",
            number,
            len(images),
            model,
            len(text),
        )
        if text:
            pages.append(text)

    return "\n\n".join(pages)
