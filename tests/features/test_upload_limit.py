"""The upload ceiling, and the two places that have to agree about it.

Embedding is ~97% of ingest cost and its rate cannot be tuned, so the size of
the file is the only place the wait is bounded at all. Before this there was no
bound: Streamlit's default of 200 MB applied, and nothing in the lane checked
at all - so a batch import or a script could hand `load_file` anything.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from src.ingestion.loader import (
    DEFAULT_MAX_UPLOAD_BYTES,
    ContentLoader,
    FileTooLargeError,
    max_upload_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_CONFIG = REPO_ROOT / ".streamlit" / "config.toml"

# Long and varied enough to clear the quality checker.
GOOD_TEXT = (
    "Diplomacy is the practice of negotiation between nations. Envoys carry "
    "instructions from their capitals and report what they learn abroad. "
    "Treaties record the settlements those talks produce, binding successors "
    "who never sat at the table. Summits gather heads of government when "
    "lower channels have stalled or when a signature needs an audience. "
    "Consular work protects citizens travelling or detained far from home."
)


def test_the_limit_is_35_mb() -> None:
    assert DEFAULT_MAX_UPLOAD_BYTES == 35 * 1024 * 1024


def test_the_widget_and_the_loader_agree() -> None:
    """Two enforcement points, one number.

    The widget refuses before the bytes are sent; the loader refuses whatever
    reaches it from the other three entry points. They drift apart silently -
    hence this test rather than a comment asking nicely.
    """
    config = tomllib.loads(STREAMLIT_CONFIG.read_text(encoding="utf-8"))
    widget_mb = config["server"]["maxUploadSize"]

    assert widget_mb * 1024 * 1024 == DEFAULT_MAX_UPLOAD_BYTES


def test_an_oversized_file_is_refused_before_it_is_parsed(tmp_path, monkeypatch) -> None:
    """Refusing on the byte count is instant; parsing a huge PDF is not."""
    monkeypatch.chdir(tmp_path)
    loader = ContentLoader()
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")

    with pytest.raises(FileTooLargeError, match="over the"):
        loader.load_file(b"x" * 2048, "huge.txt")


def test_the_message_names_the_size_and_the_limit(tmp_path, monkeypatch) -> None:
    """"Too large" without the numbers leaves you guessing by how much."""
    monkeypatch.chdir(tmp_path)
    loader = ContentLoader()
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(1024 * 1024))

    with pytest.raises(FileTooLargeError) as excinfo:
        loader.load_file(b"x" * (3 * 1024 * 1024), "textbook.pdf")

    message = str(excinfo.value)
    assert "textbook.pdf" in message
    assert "3.0 MB" in message
    assert "1 MB limit" in message


def test_a_file_within_the_limit_still_loads(tmp_path, monkeypatch) -> None:
    """The control: a check that refuses everything would pass the tests above."""
    monkeypatch.chdir(tmp_path)
    loader = ContentLoader()

    document = loader.load_file(GOOD_TEXT.encode("utf-8"), "primer.txt")

    assert document.id
    assert "Diplomacy" in document.content


def test_the_limit_is_configurable(monkeypatch) -> None:
    """A deployment with more patience can raise it without a code change."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
    assert max_upload_bytes() == 50 * 1024 * 1024


def test_a_nonsense_limit_falls_back_rather_than_crashing(monkeypatch) -> None:
    """A typo in .env must not take the upload page down."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "thirty-five megabytes")
    assert max_upload_bytes() == DEFAULT_MAX_UPLOAD_BYTES
