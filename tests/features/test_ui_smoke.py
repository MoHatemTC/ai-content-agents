"""Page-level smoke tests for the Streamlit UIs.

Every lane's logic is well covered, but nothing loaded the pages themselves,
which is how two defects reached a user unnoticed: ``src/ingestion/ui.py``
crashed on import under ``streamlit run``, and the flashcard page passed
``Chunk`` objects where chunk id strings were required.

These tests execute the pages the way Streamlit does, so that class of bug
fails in CI instead of in front of whoever is demoing.
"""

from __future__ import annotations

import typing
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.ingestion.loader import ContentLoader
from src.ingestion.schema import Chunk, Document
from src.ui_common import chunk_ids, render_current_content_status
from tests.conftest import CompliantStudyClient

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


@pytest.fixture(autouse=True)
def _no_live_calls(monkeypatch: pytest.MonkeyPatch):
    """Give every agent the pages build a fake gateway.

    These tests execute the real pages, so the pages construct their own
    agents and there is no call site to inject at. Patching the constructor
    default is the seam: an explicit ``client=`` still wins, so this only
    catches the agents the page builds for itself.

    Without it these tests make real API calls - they did, briefly, and the
    suite went from 27 s to 128 s.

    The credentials are set because the pages check whether a gateway is
    reachable before offering to generate at all, and stop with a message when
    it is not. These tests are about a *configured* deployment - one with a
    fake gateway behind it - so they have to look like one. Whether the pages
    degrade correctly when nothing is configured is a separate question, and
    ``test_page_loads`` covers it: the whole suite runs with no credentials in
    CI, and those pages must still load.
    """
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://gateway.invalid/v1")

    from src.study.flashcard_agent import FlashcardAgent
    from src.study.revision_agent import RevisionAgent
    from src.study.study_plan_agent import StudyPlanAgent

    for agent_class in (FlashcardAgent, StudyPlanAgent, RevisionAgent):
        original = agent_class.__init__

        def patched(self, *, client=None, model=None, _original=original):
            _original(
                self,
                client=client if client is not None else CompliantStudyClient(),
                model=model or "test-model",
            )

        monkeypatch.setattr(agent_class, "__init__", patched)


DOC_TITLE = "Diplomacy Primer"

# Long and varied enough to clear the ingestion quality checker, which rejects
# short or highly repetitive documents.
LIBRARY_TEXT = (
    "Diplomacy is the practice of negotiation between nations. Envoys carry "
    "instructions from their capitals and report what they learn abroad. "
    "Treaties record the settlements those talks produce, binding successors "
    "who never sat at the table. Summits gather heads of government when "
    "lower channels have stalled or when a signature needs an audience. "
    "Recognition, sanctions and the severing of relations mark the colder end "
    "of the same instrument. Multilateral bodies extend the practice beyond "
    "pairs of states, giving small powers a hearing they would not otherwise "
    "command. Consular work, less visible than any of it, protects citizens "
    "who are travelling, detained or stranded far from home."
)


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


def _document(document_id: str = "doc-1") -> Document:
    """A Document shaped exactly as the Upload page stores it."""
    return Document(
        id=document_id,
        title=DOC_TITLE,
        content=(
            "Diplomacy is the practice of negotiation between nations. "
            "Treaties, envoys and summits are its core instruments."
        ),
        source_type="paste",
        file_type="txt",
    )


def _load_content(at: AppTest, count: int = 3) -> list[Chunk]:
    """Put an active document and its chunks in session state, as upload does."""
    chunks = _chunks(count=count)
    at.session_state["current_doc"] = _document()
    at.session_state["current_chunks"] = chunks
    return chunks


def _submit_button(at: AppTest, label: str):
    """Find a form submit button by its label."""
    for button in at.button:
        if label in str(button.label):
            return button
    raise AssertionError(f"no button labelled {label!r}; saw {[b.label for b in at.button]}")


def _button_with_key(at: AppTest, key: str):
    """Find a button by the widget key the page assigned it."""
    for button in at.button:
        if button.key == key:
            return button
    raise AssertionError(f"no button keyed {key!r}; saw {[b.key for b in at.button]}")


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
    _load_content(at, count=3)
    at.run()

    at.button[0].click().run()

    assert not at.exception
    errors = [str(e.value) for e in at.error]
    assert not errors, f"page reported: {errors}"


def test_flashcards_page_records_the_chunk_ids() -> None:
    """The generated set should carry the provenance ids, not lose them."""
    from src.study.flashcard_agent import FlashcardAgent

    chunks = _chunks(count=3)
    agent = FlashcardAgent(client=CompliantStudyClient(), model="test-model")
    card_set = agent.generate(
        "Diplomacy is the practice of negotiation between nations.",
        card_format="qa",
        card_count=2,
        source_chunk_ids=[chunk.id for chunk in chunks],
    )

    assert card_set.source_chunk_ids == [chunk.id for chunk in chunks]
    assert all(isinstance(value, str) for value in card_set.source_chunk_ids)


def test_combined_app_flashcards_accepts_stored_chunks() -> None:
    """The router's flashcard page must behave identically to the standalone one.

    These two pages are duplicates of each other, and the chunk-id defect was
    fixed in one copy and missed in the other. Driving both is what makes that
    divergence fail here rather than in front of a user.
    """
    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value("🃏 Generate Flashcards").run()
    _submit_button(at, "Generate Grounded Flashcards").click().run()

    assert not at.exception
    errors = [str(e.value) for e in at.error]
    assert not errors, f"page reported: {errors}"


# --------------------------------------------------------------------------- #
# The active-content gate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "page, sidebar_choice",
    [(STUDY_UI, None), (COMBINED_APP, "🃏 Generate Flashcards")],
    ids=["study", "app"],
)
def test_generation_is_gated_until_content_is_loaded(
    page: Path, sidebar_choice: str | None
) -> None:
    """With nothing uploaded, a page must ask for content and offer no form.

    Before this gate the pages silently generated from a built-in Python-basics
    sample, so a user who had uploaded nothing - or whose upload never reached
    session state, which was every batch, library and demo import - got
    confident output about a document they had never provided.
    """
    at = AppTest.from_file(str(page), default_timeout=120)
    at.run()
    if sidebar_choice is not None:
        at.sidebar.radio[0].set_value(sidebar_choice).run()

    assert not at.exception
    warnings = [str(w.value) for w in at.warning]
    assert any("upload educational content" in text for text in warnings), warnings
    assert not [
        button
        for button in at.button
        if "Generate Grounded Flashcards" in str(button.label)
    ]


@pytest.mark.parametrize(
    "page, sidebar_choice",
    [(STUDY_UI, None), (COMBINED_APP, "🃏 Generate Flashcards")],
    ids=["study", "app"],
)
def test_active_document_header_names_the_document_and_chunk_count(
    page: Path, sidebar_choice: str | None
) -> None:
    """Both entry points must show which document they are working from."""
    at = AppTest.from_file(str(page), default_timeout=120)
    _load_content(at, count=4)
    at.run()
    if sidebar_choice is not None:
        at.sidebar.radio[0].set_value(sidebar_choice).run()

    assert not at.exception
    rendered = " ".join(str(block.value) for block in at.markdown)
    assert DOC_TITLE in rendered
    assert "4 Chunks Loaded" in rendered


def test_shared_helper_annotations_resolve() -> None:
    """The helper's annotations must name types that actually exist.

    ``from __future__ import annotations`` defers evaluation, so an undefined
    name in a signature costs nothing at import time and surfaces only when
    something resolves the hints. One copy of this helper was annotated
    ``-> tuple[Any, list, bool]`` with no ``typing`` import and shipped clean.
    """
    hints = typing.get_type_hints(render_current_content_status)

    assert hints["return"] == tuple[Document | None, list[Chunk], bool]
    assert typing.get_type_hints(chunk_ids)["return"] == list[str]


def test_chunk_ids_reduces_records_to_their_ids() -> None:
    """The conversion the agents depend on, isolated from Streamlit."""
    chunks = _chunks(count=3)

    assert chunk_ids(chunks) == ["doc-1-c0000", "doc-1-c0001", "doc-1-c0002"]
    assert chunk_ids([]) == []


# --------------------------------------------------------------------------- #
# The Content Library drives the active document
# --------------------------------------------------------------------------- #


def test_library_select_active_sets_the_current_document(tmp_path, monkeypatch) -> None:
    """"📌 Select Active" is what makes a library document reachable downstream.

    Importing through the library never touched session state, so a user could
    pick a document, move to a generation page, and be told to upload something.
    """
    monkeypatch.chdir(tmp_path)
    loader = ContentLoader()
    document = loader.load_text(LIBRARY_TEXT, title="Library Document")

    at = AppTest.from_file(str(INGESTION_UI), default_timeout=120)
    at.run()
    _button_with_key(at, f"select_{document.id}").click().run()

    assert not at.exception
    assert at.session_state["current_doc"].id == document.id
    assert at.session_state["current_chunks"]
    assert all(
        chunk.document_id == document.id for chunk in at.session_state["current_chunks"]
    )


def test_deleting_the_active_document_clears_it(tmp_path, monkeypatch) -> None:
    """Deleting the active document must not leave the pages pointing at a ghost."""
    monkeypatch.chdir(tmp_path)
    loader = ContentLoader()
    document = loader.load_text(LIBRARY_TEXT, title="Doomed Document")

    at = AppTest.from_file(str(INGESTION_UI), default_timeout=120)
    at.run()
    _button_with_key(at, f"select_{document.id}").click().run()
    assert at.session_state["current_doc"] is not None

    _button_with_key(at, f"delete_{document.id}").click().run()

    assert not at.exception
    assert at.session_state["current_doc"] is None
    assert at.session_state["current_chunks"] == []
