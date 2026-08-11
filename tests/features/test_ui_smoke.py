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
from tests.conftest import CompliantAgentsClient, CompliantStudyClient

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

    from src.agents.concept_agent import ConceptAgent
    from src.agents.mentor_agent import MentorAgent
    from src.agents.question_bank_agent import QuestionBankAgent
    from src.agents.test_help_agent import TestHelpAgent
    from src.study.flashcard_agent import FlashcardAgent
    from src.study.revision_agent import RevisionAgent
    from src.study.study_plan_agent import StudyPlanAgent

    # Mentor and concept take a different fake: CompliantAgentsClient reads the
    # [chunk_id] markers back out of the prompt and echoes real ids and real
    # text, so the reference and support checks those agents run have something
    # they can actually verify. It serves the two question agents for the same
    # reason - they verify citations too. CompliantStudyClient answers the
    # study prompts.
    for agent_class, fake in (
        (FlashcardAgent, CompliantStudyClient),
        (StudyPlanAgent, CompliantStudyClient),
        (RevisionAgent, CompliantStudyClient),
        (MentorAgent, CompliantAgentsClient),
        (ConceptAgent, CompliantAgentsClient),
        (QuestionBankAgent, CompliantAgentsClient),
        (TestHelpAgent, CompliantAgentsClient),
    ):
        original = agent_class.__init__

        def patched(self, *, client=None, model=None, _original=original, _fake=fake):
            _original(
                self,
                client=client if client is not None else _fake(),
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
    raise AssertionError(
        f"no button labelled {label!r}; saw {[b.label for b in at.button]}"
    )


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
    """ "📌 Select Active" is what makes a library document reachable downstream.

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


# --------------------------------------------------------------------------- #
# The mentor and concept pages retrieve, rather than sending the whole document
#
# These two pages had no coverage at all - the only page this file ever selected
# in src/app.py was Flashcards - which is why the defect below reached a user.
# --------------------------------------------------------------------------- #


# A document large enough that sending it whole is obviously wrong. The real
# report came from a 1,598-page textbook exceeding a 1,048,576-token limit; this
# is the same shape, small enough to keep the test fast.
BIG_DOCUMENT = (
    "Diplomacy is the practice of negotiation between nations. "
    "Treaties record the settlements those talks produce. "
    "Envoys carry instructions from their capitals. "
) * 400


def _big_document(document_id: str = "doc-big") -> Document:
    return Document(
        id=document_id,
        title="Diplomacy Primer (long)",
        content=BIG_DOCUMENT,
        source_type="paste",
        file_type="txt",
    )


def _load_big_content(at: AppTest, count: int = 40) -> None:
    at.session_state["current_doc"] = _big_document()
    at.session_state["current_chunks"] = _chunks(document_id="doc-big", count=count)


@pytest.mark.parametrize(
    "page_label,button_label",
    [
        ("🧭 Mentor", "Generate Mentor Response"),
        ("💡 Concept Explanation", "Generate Concept Explanation"),
    ],
    ids=["mentor", "concept"],
)
def test_the_page_generates_from_uploaded_content(page_label, button_label) -> None:
    """The basic thing neither page had a test for: it runs at all."""
    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, button_label).click().run()

    assert not at.exception
    errors = [str(e.value) for e in at.error]
    assert not errors, f"page reported: {errors}"


@pytest.mark.parametrize(
    "page_label,button_label",
    [
        ("🧭 Mentor", "Generate Mentor Response"),
        ("💡 Concept Explanation", "Generate Concept Explanation"),
    ],
    ids=["mentor", "concept"],
)
def test_the_whole_document_is_not_sent_to_the_model(
    page_label, button_label, monkeypatch
) -> None:
    """The reported bug: a 1,598-page textbook went to the model verbatim.

    ``ContextWindowExceededError: The input token count exceeds the maximum
    number of tokens allowed (1048576)``. Both pages passed ``doc.content``
    while the three study pages retrieved first.

    Asserting on the *prompt the model received* is what makes this specific.
    A test that only checked the page did not error would pass either way, since
    a small document fits regardless.
    """
    prompts: list[str] = []

    from tests.conftest import CompliantAgentsClient

    original_create = CompliantAgentsClient.create

    def recording_create(self, **kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        return original_create(self, **kwargs)

    monkeypatch.setattr(CompliantAgentsClient, "create", recording_create)

    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_big_content(at)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, button_label).click().run()

    assert not at.exception
    assert prompts, "the page never called the model"

    prompt = prompts[0]
    assert BIG_DOCUMENT not in prompt, (
        "the whole document reached the model - this is the "
        "ContextWindowExceededError bug"
    )
    assert len(prompt) < len(BIG_DOCUMENT), (
        f"prompt ({len(prompt):,} chars) is not smaller than the document "
        f"({len(BIG_DOCUMENT):,} chars); retrieval did not narrow anything"
    )
    # Retrieval happened rather than the content simply being dropped.
    assert "doc-big-c" in prompt, "no retrieved chunk markers in the prompt"


# --------------------------------------------------------------------------- #
# "Sources" has to be earned
#
# The section was headed "Provenance references" while nothing verified it:
# verify_references only runs when the agent is handed a GroundedContext, and
# these pages deliberately do not pass one (issue #33). A model could invent a
# chunk id and the page would present it as a source.
# --------------------------------------------------------------------------- #


class _CitesAnInventedChunk:
    """A gateway that answers correctly but cites a chunk that does not exist."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        import json as _json

        self.calls.append(kwargs)
        # Answer whichever agent asked. This used to send `definition` and
        # `next_steps` together so one payload would satisfy both schemas;
        # with extra="forbid" that is now rejected before the grounding check
        # it is here to exercise - which is the point of forbidding extras.
        prompt = kwargs["messages"][0]["content"]
        payload = {
            "explanation": "Diplomacy is the practice of negotiation.",
            "key_points": ["Envoys carry instructions."],
            "references": [
                {"segment_id": "doc-1-c9999", "text": "a passage never retrieved"}
            ],
            "requires_human_review": True,
        }
        if "next_steps" in prompt:
            payload["next_steps"] = ["Read the treaty chapter."]
        else:
            payload["definition"] = "Diplomacy is the practice of negotiation."
        body = _json.dumps(payload)
        message = type("M", (), {"content": body})
        choice = type("C", (), {"message": message, "finish_reason": "stop"})
        return type("R", (), {"choices": [choice], "error": None})


@pytest.mark.parametrize(
    "page_label,button_label",
    [
        ("🧭 Mentor", "Generate Mentor Response"),
        ("💡 Concept Explanation", "Generate Concept Explanation"),
    ],
    ids=["mentor", "concept"],
)
def test_an_invented_citation_is_flagged_not_displayed_as_a_source(
    page_label, button_label, monkeypatch
) -> None:
    """A citation the retriever never returned must not read as provenance.

    Relabelling without this check would make things worse: an invented
    citation rendered as "Passage 5 - Diplomacy Primer" is far more convincing
    than the raw UUID it replaced.
    """
    from src.agents.concept_agent import ConceptAgent
    from src.agents.mentor_agent import MentorAgent

    for agent_class in (MentorAgent, ConceptAgent):
        original = agent_class.__init__

        def patched(self, *, client=None, model=None, _original=original):
            _original(self, client=_CitesAnInventedChunk(), model="test-model")

        monkeypatch.setattr(agent_class, "__init__", patched)

    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, button_label).click().run()

    assert not at.exception
    warnings = " ".join(str(w.value) for w in at.warning)

    # The page now passes a GroundedContext, so the agent verifies citations
    # itself and refuses outright - stronger than the previous behaviour, which
    # rendered the answer with an "Unverified citation" caveat beside it.
    # render_provenance still carries that caveat as defence in depth for any
    # caller that does not supply a context.
    assert "withheld by the grounding check" in warnings, (
        "an invented chunk id was presented as a source"
    )
    assert "doc-1-c9999" in warnings


@pytest.mark.parametrize(
    "page_label,button_label",
    [
        ("🧭 Mentor", "Generate Mentor Response"),
        ("💡 Concept Explanation", "Generate Concept Explanation"),
    ],
    ids=["mentor", "concept"],
)
def test_a_real_citation_is_shown_as_a_readable_passage(
    page_label, button_label
) -> None:
    """The other half: a genuine citation must not be flagged.

    A check that rejects everything would satisfy the test above.
    """
    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, button_label).click().run()

    assert not at.exception
    warnings = " ".join(str(w.value) for w in at.warning)
    assert "Unverified citation" not in warnings, (
        "a genuine citation was flagged as invented"
    )

    rendered = " ".join(str(m.value) for m in at.markdown)
    assert "Passage " in rendered, "no readable passage label was rendered"


# --------------------------------------------------------------------------- #
# The Question Bank and Test Help pages
#
# Both agents were built, tested and documented in Sprint 4 and then had no
# interface at all - not a page in src/app.py, and frontend/qbank_ui.py was
# `def render(): pass`. The only way to reach either was a pytest file.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "page_label",
    ["📝 Question Bank", "🎯 Test Help"],
    ids=["question_bank", "test_help"],
)
def test_the_question_page_generates_from_uploaded_content(page_label) -> None:
    """The basic thing neither page could do before: run at all."""
    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, "Generate Questions").click().run()

    assert not at.exception
    errors = [str(e.value) for e in at.error]
    assert not errors, f"page reported: {errors}"

    rendered = " ".join(str(block.value) for block in at.markdown)
    assert "PENDING HUMAN REVIEW" in rendered


@pytest.mark.parametrize(
    "page_label",
    ["📝 Question Bank", "🎯 Test Help"],
    ids=["question_bank", "test_help"],
)
def test_the_question_page_queues_its_output_for_review(
    page_label, tmp_path, monkeypatch
) -> None:
    """The badge has to mean something.

    The page cannot be handed a store - it builds its own - so this points
    PLATFORM_DB_PATH at a temporary file and reads the queue back out. Without
    it the page would write into the repo's ingestion.db during the test run.
    """
    monkeypatch.setenv("PLATFORM_DB_PATH", str(tmp_path / "platform.db"))

    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_content(at, count=3)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, "Generate Questions").click().run()

    assert not at.exception

    from src.validation.review_schema import OutputStatus
    from src.validation.store import PlatformStore

    store = PlatformStore(db_path=str(tmp_path / "platform.db"))
    queued = store.list_outputs(status=OutputStatus.PENDING)
    assert queued, "the page printed PENDING but queued nothing for review"


@pytest.mark.parametrize(
    "page_label",
    ["📝 Question Bank", "🎯 Test Help"],
    ids=["question_bank", "test_help"],
)
def test_the_question_page_retrieves_instead_of_sending_the_document(
    page_label, monkeypatch
) -> None:
    """The same defect the mentor and concept pages shipped (issue #33).

    Asserting on the prompt the model received is what makes this specific; a
    page that merely does not error would pass either way on a small document.
    """
    prompts: list[str] = []
    original_create = CompliantAgentsClient.create

    def recording_create(self, **kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        return original_create(self, **kwargs)

    monkeypatch.setattr(CompliantAgentsClient, "create", recording_create)

    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    _load_big_content(at)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()
    _submit_button(at, "Generate Questions").click().run()

    assert not at.exception
    assert prompts, "the page never called the model"
    assert BIG_DOCUMENT not in prompts[0], "the whole document reached the model"
    assert "doc-big-c" in prompts[0], "no retrieved chunk markers in the prompt"


@pytest.mark.parametrize(
    "page_label",
    ["📝 Question Bank", "🎯 Test Help"],
    ids=["question_bank", "test_help"],
)
def test_the_question_page_is_gated_until_content_is_loaded(page_label) -> None:
    """With nothing uploaded, the page asks for content and offers no form."""
    at = AppTest.from_file(str(COMBINED_APP), default_timeout=120)
    at.run()

    at.sidebar.radio[0].set_value(page_label).run()

    assert not at.exception
    warnings = [str(w.value) for w in at.warning]
    assert any("upload educational content" in text for text in warnings), warnings
    assert not [
        button for button in at.button if "Generate Questions" in str(button.label)
    ]
