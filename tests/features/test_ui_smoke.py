"""Page-level smoke tests for the Streamlit UIs.

Every lane's logic is well covered, but nothing loaded the pages themselves,
which is how two defects reached a user unnoticed: ``src/ingestion/ui.py``
crashed on import under ``streamlit run``, and the flashcard page passed
``Chunk`` objects where chunk id strings were required.

These tests execute the pages the way Streamlit does, so that class of bug
fails in CI instead of in front of whoever is demoing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.ingestion.schema import Chunk

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDY_UI = REPO_ROOT / "src" / "study" / "ui.py"
INGESTION_UI = REPO_ROOT / "src" / "ingestion" / "ui.py"
COMBINED_APP = REPO_ROOT / "src" / "app.py"


@pytest.fixture(autouse=True)
def _clear_streamlit_caches():
    """Keep cached resources from leaking between page runs."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _chunks(document_id: str = "doc-1", count: int = 3) -> list[Chunk]:
    """Chunk records shaped exactly as the Upload page stores them."""
    return [
        Chunk(
            id=f"{document_id}-c{index:04d}",
            document_id=document_id,
            text=f"Diplomacy paragraph {index} about treaties and negotiation.",
            ordinal=index,
        )
        for index in range(count)
    ]


# --------------------------------------------------------------------------- #
# Pages load at all
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "page", [STUDY_UI, INGESTION_UI, COMBINED_APP], ids=["study", "ingestion", "app"]
)
def test_page_loads(page: Path) -> None:
    """Each page must execute as a script, the way `streamlit run` executes it.

    ``src/ingestion/ui.py`` used relative imports, which cannot resolve when the
    file is run as ``__main__``, so it raised ImportError for every visitor while
    the server itself looked healthy.
    """
    at = AppTest.from_file(str(page), default_timeout=120)
    at.run()

    assert not at.exception, f"{page.name} raised {at.exception}"


# --------------------------------------------------------------------------- #
# The flashcard page passes chunk *ids*, not Chunk objects
# --------------------------------------------------------------------------- #


def test_flashcards_page_accepts_stored_chunks() -> None:
    """Generating from uploaded content must not explode on the stored chunks.

    The Upload page stores ``Chunk`` objects in ``session_state.current_chunks``.
    The flashcard page forwarded them straight into ``source_chunk_ids``, which
    is ``list[str]``, so pydantic rejected every element - one validation error
    per chunk in the uploaded document.
    """
    at = AppTest.from_file(str(STUDY_UI), default_timeout=120)
    at.session_state["current_chunks"] = _chunks(count=3)
    at.run()

    at.button[0].click().run()

    assert not at.exception
    errors = [str(e.value) for e in at.error]
    assert not errors, f"page reported: {errors}"


def test_flashcards_page_records_the_chunk_ids() -> None:
    """The generated set should carry the provenance ids, not lose them."""
    from src.study.flashcard_agent import FlashcardAgent

    chunks = _chunks(count=3)
    card_set = FlashcardAgent(mock_mode=True).generate(
        "Diplomacy is the practice of negotiation between nations.",
        card_format="qa",
        card_count=2,
        source_chunk_ids=[chunk.id for chunk in chunks],
    )

    assert card_set.source_chunk_ids == [chunk.id for chunk in chunks]
    assert all(isinstance(value, str) for value in card_set.source_chunk_ids)
