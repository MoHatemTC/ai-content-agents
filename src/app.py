
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st

from src.study.batch import default_demo_dataset, run_full_batch
from src.study.evaluation import benchmark_quality
from src.ingestion.loader import ContentLoader
from src.ingestion.batch import BatchIngestion
from src.ingestion.library import ContentLibrary
from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from src.ingestion.demo_data import DemoDataLoader
from src.llm_gateway import gateway_availability
from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_flashcard_set,
    format_revision_session,
    format_study_plan,
)
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent
from src.schemas import FlashcardSet
from src.study.schemas import RevisionSession, StudyPlan
from src.services.mentor_concept import MentorConceptService
from src.ui_common import render_current_content_status, render_provenance
from src.retrieval import ChunkIndex, RetrievalConfig
from src.study.grounding import (
    NoGroundingError,
    ensure_document_indexed,
    grounded_content,
)

# ---------------------------------------------------------------------------
# Initialize shared services
# ---------------------------------------------------------------------------
@st.cache_resource
def get_loader():
    return ContentLoader()

@st.cache_resource
def get_batch():
    return BatchIngestion()


@st.cache_resource
def get_library():
    return ContentLibrary()


@st.cache_resource
def get_demo():
    return DemoDataLoader()

@st.cache_resource
def get_flashcard_agent():
    return FlashcardAgent()

@st.cache_resource
def get_study_plan_agent():
    return StudyPlanAgent()

@st.cache_resource
def get_revision_agent():
    return RevisionAgent()


@st.cache_resource
def get_question_bank_agent():
    return QuestionBankAgent()


@st.cache_resource
def get_test_help_agent():
    return TestHelpAgent()


@st.cache_resource
def get_chunk_index():
    """The retrieval index, persisted when CHROMA_DIR is set.

    Embedding a large document costs minutes and the rate cannot be tuned, so
    the only way not to pay it repeatedly is not to throw it away. Without a
    persist directory Chroma runs in memory and every restart re-embeds
    everything from scratch.

    Left unset the index stays in memory, which keeps tests and fresh clones
    free of on-disk state.
    """
    directory = os.getenv("CHROMA_DIR", "").strip()
    config = RetrievalConfig(persist_directory=directory) if directory else None
    return ChunkIndex(config=config)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PENDING_BADGE = ":warning: **PENDING HUMAN REVIEW — not final.**"


def ensure_indexed(show_progress: bool = False) -> bool:
    """Embed the active document's chunks if that has not happened yet.

    Embedding is 97% of ingest cost - 115s for a 1,598-page textbook, against
    5s to parse it - and the rate is fixed, so the question is not how to make
    it faster but where the learner has to stand and wait for it. Doing it on
    upload, where a wait is expected and progress is visible, is far better than
    doing it on the Generate click, where it reads as the app having hung.

    Called from the upload page for that reason, and again from :func:`ground`
    as a fallback, so a document ingested before this existed still works
    without being re-uploaded.

    Args:
        show_progress: Show a progress message. True on the upload page, where
            the wait is the point; False on generation, where it is a fallback.

    Returns:
        Whether any indexing was actually performed.
    """
    doc = st.session_state.get("current_doc")
    chunks = st.session_state.get("current_chunks") or []
    if doc is None or not chunks:
        return False

    # session_state is the in-session fast path - it saves a Chroma round-trip
    # on every rerun. It is not the record of truth: it is empty in a new
    # session, so on its own it re-embeds a document that is already indexed.
    indexed = st.session_state.setdefault("indexed_documents", set())
    if doc.id in indexed:
        return False

    index = get_chunk_index()
    if index.document_chunk_count(doc.id) == len(chunks):
        indexed.add(doc.id)
        return False

    message = f"Preparing {len(chunks):,} passages for retrieval..."
    if show_progress:
        with st.status(message, expanded=False) as status:
            performed = ensure_document_indexed(index, doc.id, chunks)
            status.update(label=f"Indexed {len(chunks):,} passages", state="complete")
    else:
        with st.spinner(message):
            performed = ensure_document_indexed(index, doc.id, chunks)

    indexed.add(doc.id)
    return performed


def ground(focus: str, topics: list[str]):
    """Retrieve the passages this generation should be built from.

    Args:
        focus: What the learner asked the material to cover; may be blank.
        topics: Extracted topics, used as the query when ``focus`` is blank.

    Returns:
        A ``(content, chunk_ids, context)`` triple. The mentor and concept
        agents take the ``GroundedContext`` itself, which is what turns on their
        reference and support checks; the study agents only need the text.

        This used to discard the context with ``_``, which is why the mentor and
        concept pages were sending whole documents to the model - the object
        they needed was already being built here and thrown away.

    Raises:
        NoGroundingError: If nothing could be retrieved.
    """
    ensure_indexed()
    doc = st.session_state.get("current_doc")

    return grounded_content(
        index=get_chunk_index(), document_id=doc.id, focus=focus, topics=topics
    )



# ---------------------------------------------------------------------------
# Shared page renderer: Question Bank + Test Help
#
# Both agents were built, tested and documented in Sprint 4 and then had no
# interface anywhere: no page here, and `frontend/qbank_ui.py` was
# `def render(): pass`. The only way to run either was a pytest file.
#
# The two pages differ in one line of copy and which agent they call, so one
# renderer serves both. Two hand-maintained copies of the same page is how the
# agents behind them drifted apart in the first place (BUG-08/09).
# ---------------------------------------------------------------------------
def _render_question_page(agent, *, title: str, caption: str, form_key: str) -> None:
    """Render a grounded question-generation page for human review.

    Args:
        agent: A :class:`~src.agents.question_agent_base.QuestionAgentBase`.
        title: Page heading.
        caption: One-line description under the heading.
        form_key: Unique Streamlit form key.
    """
    st.title(title)
    st.caption(caption)
    doc, chunks, is_loaded = render_current_content_status()

    if not is_loaded:
        return

    content = doc.content
    with st.form(form_key):
        col1, col2 = st.columns(2)
        with col1:
            question_type = st.selectbox(
                "Question type",
                ["mcq", "true_false", "short_answer"],
                key=f"{form_key}_type",
            )
            difficulty = st.selectbox(
                "Difficulty",
                ["beginner", "intermediate", "advanced"],
                key=f"{form_key}_difficulty",
            )
        with col2:
            num_questions = st.slider(
                "Number of questions",
                min_value=1,
                max_value=20,
                value=5,
                key=f"{form_key}_count",
            )
            focus = st.text_input(
                "What should these cover?",
                placeholder="e.g. thermal conduction",
                help=(
                    "Used to retrieve the relevant passages. Leave blank to "
                    "draw on the document's main topics."
                ),
                key=f"{form_key}_focus",
            )
        submitted = st.form_submit_button("Generate Questions")

    if not submitted:
        return

    require_generation()
    try:
        # Same wiring as the mentor and concept pages: the focus is the
        # retrieval query, the allow-list is the fallback when it is blank.
        allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
        grounded, cited, context = ground(focus, allow_list)
        with st.spinner("Generating questions..."):
            # generate_reviewable, not generate: a page that prints PENDING
            # HUMAN REVIEW over an output no reviewer can see is the defect
            # #39 and #40 existed to fix. These two agents had no gate at all
            # because, until now, nothing called them.
            reviewable = agent.generate_reviewable(
                grounded,
                question_type=question_type,
                difficulty=difficulty,
                num_questions=num_questions,
                context=context,
            )
        payload = reviewable.payload
    except NoGroundingError as exc:
        st.error(str(exc))
    except ValueError as exc:
        # The agent holds the reply to what was asked for and verifies every
        # citation. A rejection here is a quality gate doing its job - the
        # model returned the wrong count, the wrong type, or cited something
        # that does not exist - and it must not read as a crash.
        st.warning(f"**Output withheld by the quality checks.** {exc}")
        st.caption(
            "Try a smaller number of questions, or a topic the uploaded "
            "document covers in more depth."
        )
    except Exception as error:
        st.error(f"Error generating questions: {error}")
    else:
        st.success(f"Generated {len(payload.get('questions', []))} questions")
        st.markdown(PENDING_BADGE)
        st.write(f"Review status: **{reviewable.status.value.upper()}**")
        # The support heuristic is advisory, not a gate - it rejected 5 of 20
        # correct live generations, so it flags rather than blocks. Shown here
        # and recorded on the review record, exactly as mentor and concept do.
        for warning in (reviewable.validation_report or {}).get(
            "grounding_warnings", []
        ):
            st.caption(f":orange[⚑ {warning}]")
        for index, item in enumerate(payload.get("questions", []), start=1):
            with st.expander(f"{index}. {item.get('question', '')}"):
                options = item.get("options")
                if options:
                    for option in options:
                        marker = "✅" if option == item.get("correct_answer") else "•"
                        st.markdown(f"{marker} {option}")
                else:
                    st.markdown(f"**Answer:** {item.get('correct_answer', '')}")
                st.caption(f"Why: {item.get('rationale', '')}")
                st.caption(
                    f"Type: {item.get('type', '')}  ·  "
                    f"Difficulty: {item.get('difficulty', '')}"
                )
                render_provenance(item.get("references", []), cited, title=doc.title)
        with st.expander("JSON payload (for export gate)"):
            st.json(payload)


# ---------------------------------------------------------------------------
# Page config + sidebar nav
# ---------------------------------------------------------------------------
def get_mentor_concept_service():
    return MentorConceptService()

# Set page config
st.set_page_config(page_title="AI Study Assistant", page_icon="📚", layout="wide")

st.sidebar.title("📚 AI Study Assistant")
page = st.sidebar.radio(
    "Choose a page",
    [
        "🏠 Home",
        "📤 Upload Content",
        "🃏 Generate Flashcards",
        "📅 Study Plan",
        "🔄 Revision Plan",
        "📦 Batch & Benchmark",
        "🧭 Mentor",
        "💡 Concept Explanation",
        "📝 Question Bank",
        "🎯 Test Help",
    ]
)

loader = get_loader()
batch = get_batch()
library = get_library()
demo = get_demo()

# Say whether generation can actually happen. The app spent weeks serving
# placeholder cards - "See the source text for a fuller treatment" - because
# the UI forced mock mode regardless of config and nothing on screen said so.
# Mock mode is gone; what is left worth showing is whether the gateway is
# reachable, and which model answers.
#
# The agents are built only when it is, because building one without
# credentials raises: an unconfigured deployment must land on the message
# below rather than on a traceback where the page should be. Everything that
# does not need a model - upload, the library, review queues - keeps working.
_gateway_ready, _gateway_reason = gateway_availability()

fc_agent = sp_agent = rv_agent = mentor_concept_service = None
qbank_agent = test_help_agent = None
if _gateway_ready:
    fc_agent = get_flashcard_agent()
    sp_agent = get_study_plan_agent()
    rv_agent = get_revision_agent()
    mentor_concept_service = get_mentor_concept_service()
    qbank_agent = get_question_bank_agent()
    test_help_agent = get_test_help_agent()
    st.sidebar.caption(f"🟢 Live · `{fc_agent.model}`")
else:
    st.sidebar.error(
        f"**Generation unavailable** — {_gateway_reason}. Upload, the library "
        "and the review queue still work; anything that calls a model does not."
    )


def require_generation() -> None:
    """Halt the page with a clear message when no model can be reached.

    Without this the agents are ``None`` and the first call raises
    ``AttributeError: 'NoneType' object has no attribute 'generate'``, which
    tells whoever is looking at it nothing about the cause.
    """
    if not _gateway_ready:
        st.error(
            f"Generation unavailable — {_gateway_reason}. Set LITELLM_API_KEY "
            "and LITELLM_BASE_URL in .env, then reload."
        )
        st.stop()


# ---------------------------------------------------------------------------
# Page: Home
# ---------------------------------------------------------------------------
if page == "🏠 Home":
    st.title("Welcome to AI Study Assistant!")
    st.markdown("""
    This unified app wires together Sprint 2 (content ingestion) and
    Sprint 3 (flashcards / study plan / revision assistant). Every
    generated output is explicitly **marked for human review** and routed
    through the shared `src.validation.review_schema` gate before
    export.

    - **Content Ingestion** — Upload / paste TXT, PDF, DOCX, Markdown.
    - **Flashcard Generator** — grounded term-definition or Q-A cards
      with count + format controls.
    - **Study Plan** — difficulty + time-budgeted plan built from real
      content topics (never fabricates a topic).
    - **Revision Assistant** — targeted revision items on your selected
      weak topics, using a spaced-repetition heuristic.
    - **Batch & Benchmark** — full-demo run plus groundedness / quality
      scores for the AI evaluation workstream.
    """)


# ---------------------------------------------------------------------------
# Page: Upload Content (unchanged Sprint 2 upload)
# ---------------------------------------------------------------------------
elif page == "📤 Upload Content":
    st.title("Upload Content")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📁 Upload File",
    "📝 Paste Text",
    "📂 Batch Upload",
    "📚 Content Library",
    "🎓 Demo Dataset",
    ])
    
    with tab1:
        uploaded_file = st.file_uploader(
            "Choose a file", type=["txt", "pdf", "docx", "md"]
        )
        if uploaded_file is not None:
            try:
                with st.spinner("Processing file..."):
                    file_content = uploaded_file.read()
                    doc = loader.load_file(file_content, uploaded_file.name)
                    chunks = loader.store.get_chunks_by_document_id(doc.id)
                    st.success(f"Successfully uploaded {doc.title}!")
                    st.session_state.current_doc = doc
                    st.session_state.current_chunks = chunks
                    st.write(f"Document ID: {doc.id}")
                    st.write(f"Number of chunks: {len(chunks)}")
                    with st.expander("View Document Content"):
                        st.text(
                            doc.content[:2000] + "..."
                            if len(doc.content) > 2000
                            else doc.content
                        )
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")

    with tab2:
        title = st.text_input("Title (optional)", "Pasted Text")
        pasted_text = st.text_area("Paste your text here", height=200)
        if st.button("Process Text") and pasted_text:
            try:
                progress = st.progress(0, text="Starting upload...")

                progress.progress(30, text="Reading Text...")
                document = loader.load_text(
                    text=pasted_text,
                    title=title,
                )

                progress.progress(80, text="Generating chunks...")
                chunks = loader.store.get_chunks_by_document_id(document.id)

                progress.progress(100, text="Text Upload complete!")
                progress.empty()

                st.success(f"Successfully processed {document.title}!")
                st.session_state.current_doc = document
                st.session_state.current_chunks = chunks
                    
                st.write(f"Document ID: {document.id}")
                st.write(f"Number of chunks: {len(chunks)}")
                    
                with st.expander("View Document Content"):
                      st.text(document.content[:2000] + "..." if len(document.content) > 2000 else document.content)
            except Exception as e:
                st.error(f"Error processing text: {str(e)}")



    with tab3:
        st.subheader("Batch Upload")

        uploaded_files = st.file_uploader(
            "Choose multiple files",
            type=["txt", "pdf", "docx", "md"],
            accept_multiple_files=True,
            key="batch_upload",
        )

        if st.button("Upload Files", key="upload_files"):

            if not uploaded_files:
                st.warning("Please select one or more files.")

            else:
                files = [
                    (file.name, file.read())
                    for file in uploaded_files
                ]

                progress = st.progress(0, text="Preparing batch upload...")

                progress.progress(25, text="Reading selected files...")
                result = batch.ingest_files(files)

                progress.progress(100, text="Batch upload complete!")
                progress.empty()
                if result.documents:
                    st.session_state.current_doc = result.documents[0]
                    st.session_state.current_chunks = loader.store.get_chunks_by_document_id(result.documents[0].id)
                    st.success(
                        f"Successfully uploaded {len(result.documents)} file(s). Set '{result.documents[0].title}' as active content."
                    )

                if result.failed_files:
                    st.warning(
                        f"{len(result.failed_files)} file(s) could not be processed."
                    )

                    for failed in result.failed_files:
                        st.error(f"{failed.filename}: {failed.error}")
    with tab4:
        st.subheader("Content Library")

        # Optional refresh button
        st.button("Refresh Library", key="refresh_library")

        # Always load the documents
        documents = library.list_documents()
    
        if not documents:
            st.info("No documents have been uploaded yet.")
    
        else:
            current_id = getattr(st.session_state.get("current_doc"), "id", None)
            for doc in documents:
                col1, col2 = st.columns([4, 2])
                
                with col1:
                    active_badge = " 🟢 **[ACTIVE]**" if current_id == doc.id else ""
                    st.markdown(f"### {doc.title}{active_badge}")
                    st.write(f"**Source:** {doc.source_type}")
                    st.write(f"**Type:** {doc.file_type}")
                    st.write(f"**Size:** {doc.size}")
                    st.write(f"**Chunks:** {doc.chunk_count}")
                    st.write(
                        f"**Created:** {doc.created_at.strftime('%Y-%m-%d %H:%M')}"
                    )
                
                with col2:
                    if st.button(
                        "📌 Select Active",
                        key=f"select_{doc.id}"
                    ):
                        loaded_doc = library.get_document(doc.id)
                        if loaded_doc:
                            chunks = loader.store.get_chunks_by_document_id(doc.id)
                            st.session_state.current_doc = loaded_doc
                            st.session_state.current_chunks = chunks
                            st.success(f"Selected '{loaded_doc.title}' as active content!")
                            st.rerun()
                    if st.button(
                                 "🗑️ Delete",
                                key=f"delete_{doc.id}"
                                ):
                        if library.delete_document(doc.id):
                            if current_id == doc.id:
                                st.session_state.current_doc = None
                                st.session_state.current_chunks = []
                            st.success(f"{doc.title} deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to delete document.")
                
                st.divider()
                
    
    with tab5:
            st.subheader("Demo Dataset")
    
            st.write(
                "Load a sample educational dataset into the content library."
            )
    
            if st.button("Load Demo Dataset", key="load_demo"):
    
                try:
                    progress = st.progress(0, text="Loading demo dataset...")

                    count = demo.load_demo_data()

                    docs = library.list_documents()
                    if docs:
                        loaded_doc = library.get_document(docs[0].id)
                        if loaded_doc:
                            chunks = loader.store.get_chunks_by_document_id(loaded_doc.id)
                            st.session_state.current_doc = loaded_doc
                            st.session_state.current_chunks = chunks

                    progress.progress(100, text="Demo dataset loaded!")
                    progress.empty()

                    st.success(
                               f"Successfully loaded {count} demo document(s)."
                    )

                    st.rerun()
    
                except Exception as e:
                    st.error(f"Failed to load demo dataset: {e}")

    # One call covers all five ingestion paths above - single file, paste,
    # batch, library and demo - because each of them sets current_doc and
    # Streamlit reruns this script afterwards. Indexing here means the wait
    # lands on the page where the learner just asked for work to be done,
    # rather than on their first Generate click.
    ensure_indexed(show_progress=True)


# Page: Generate Flashcards
elif page == "🃏 Generate Flashcards":
    st.title("🃏 Grounded Flashcard Generator")
    doc, chunks, is_loaded = render_current_content_status()

    if is_loaded:
        content = doc.content
        with st.form("fc_form"):
            col1, col2 = st.columns(2)
            with col1:
                card_format = st.radio(
                    "Card format", ["term-definition", "qa"], horizontal=True,
                    help="term-definition: front = term. Q-A: front = a question.",
                )
                card_count = st.slider("Card count", min_value=1, max_value=25, value=8)
                focus = st.text_input(
                    "What should these cover?",
                    placeholder="e.g. thermal conduction",
                    help=(
                        "Used to retrieve the relevant passages. Leave blank to "
                        "draw on the document's main topics."
                    ),
                )
            with col2:
                allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
                st.caption(f"Extracted topic allow-list ({len(allow_list)} topics):")
                st.write(", ".join(allow_list) if allow_list else "(none)")
            submitted = st.form_submit_button("Generate Grounded Flashcards")

        if submitted:
            require_generation()
            try:
                grounded, cited, _context = ground(focus, allow_list)
                with st.spinner("Generating cards..."):
                    # generate_reviewable, not generate: the plain call returned
                    # a set flagged needs_human_review and persisted nothing, so
                    # the badge below was the only trace a review was ever due.
                    reviewable = fc_agent.generate_reviewable(
                        grounded,
                        card_format=card_format,
                        card_count=card_count,
                        source_chunk_ids=cited,
                    # The list the widget above offered, so the agent
                    # cannot reject a topic this page just showed.
                        extracted_topics=allow_list,
                    )
                    card_set = FlashcardSet.model_validate(reviewable.payload)
            except NoGroundingError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Failed to generate flashcards: {exc}")
            else:
                st.success(f"Generated {len(card_set.cards)} grounded cards")
                st.markdown(PENDING_BADGE)
                st.subheader(card_set.title)
                if card_set.description:
                    st.write(card_set.description)
                st.caption(
                    "Source topics (from allow-list only): "
                    + ", ".join(card_set.source_topics)
                )
                for i, card in enumerate(card_set.cards, start=1):
                    with st.expander(f"{i}. {card.front}"):
                        st.markdown(f"**Back:** {card.back}")
                        st.caption(
                            f"Format: {card.format}  ·  Topic: {card.source_topic}"
                        )
                        if card.tags:
                            st.caption(f"Tags: {', '.join(card.tags)}")
                with st.expander("JSON payload (for export gate)"):
                    st.json(format_flashcard_set(card_set))


# ---------------------------------------------------------------------------
# Page: Study Plan (Sprint 3 polished agent)
# ---------------------------------------------------------------------------
elif page == "📅 Study Plan":
    st.title("📅 Grounded Study Plan")
    doc, chunks, is_loaded = render_current_content_status()
    from datetime import date as _date

    if is_loaded:
        content = doc.content
        title = doc.title
        today = _date.today()
        with st.form("sp_form"):
            col1, col2 = st.columns(2)
            with col1:
                goal = st.text_input("Learner goal", f"Master the concepts in: {title}")
                difficulty = st.radio(
                    "Overall difficulty", ["easy", "medium", "hard"], horizontal=True
                )
                hours_per_week = st.slider("Hours per week", min_value=1, max_value=30, value=10)
            with col2:
                start_date = st.date_input("Plan start", today)
                end_date = st.date_input("Plan end", today + timedelta(days=28))
                allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
                st.caption(f"Planner may only schedule these {len(allow_list)} topics:")
                st.write(", ".join(allow_list) if allow_list else "(none)")
            submitted = st.form_submit_button("Generate Grounded Study Plan")

        if submitted:
            require_generation()
            try:
                # The learner goal is already the best description of what the
                # plan should cover, so it doubles as the retrieval query.
                grounded, _cited, _context = ground(goal, allow_list)
                with st.spinner("Building study plan..."):
                    reviewable = sp_agent.generate_reviewable(
                        grounded,
                        source_chunk_ids=_cited,
                        extracted_topics=allow_list,
                        learner_goal=goal,
                        difficulty=difficulty,
                        start_date=start_date,
                        end_date=end_date,
                        hours_per_week=float(hours_per_week),
                    )
                    plan = StudyPlan.model_validate(reviewable.payload)
            except NoGroundingError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Failed to build study plan: {exc}")
            else:
                st.success("Study plan ready (pending review)")
                st.markdown(PENDING_BADGE)
                st.subheader(plan.goal)
                st.caption(
                    f"{plan.start_date} → {plan.end_date} · difficulty={plan.overall_difficulty} · "
                    f"{plan.available_hours_per_week} h/week"
                )
                st.caption(
                    "Scheduled source topics: " + ", ".join(plan.source_topics)
                )
                for s in plan.topic_schedule:
                    with st.expander(f"📌 {s.topic} ({s.difficulty})"):
                        st.write(f"Dates: {s.start_date} → {s.end_date}")
                        st.write(f"Duration: {s.duration_hours} hours")
                        if s.resources:
                            st.caption(f"Resources: {', '.join(s.resources)}")
                with st.expander("JSON payload"):
                    st.json(format_study_plan(plan))


# ---------------------------------------------------------------------------
# Page: Revision Plan (Sprint 3 polished agent)
# ---------------------------------------------------------------------------
elif page == "🔄 Revision Plan":
    st.title("🔄 Targeted Revision Assistant")
    doc, chunks, is_loaded = render_current_content_status()
    from datetime import date as _date

    if is_loaded:
        content = doc.content
        allow_list = FlashcardAgent.extract_topics(content, max_topics=40)
        if not allow_list:
            allow_list = ["General topic"]
        with st.form("rv_form"):
            col1, col2 = st.columns(2)
            with col1:
                selected = st.multiselect(
                    "Weak / selected topics to revise",
                    options=allow_list,
                    default=allow_list[: min(3, len(allow_list))],
                    help="Only topics from the extracted allow-list are eligible.",
                )
                session_date = st.date_input("Session date", _date.today())
            with col2:
                st.caption("Eligible topics (from content only):")
                st.write(", ".join(allow_list))
            submitted = st.form_submit_button("Generate Revision Items")

        if submitted:
            if not selected:
                st.warning("Pick at least one topic to revise.")
            else:
                require_generation()
                try:
                    # The chosen weak topics say exactly which passages this
                    # session needs, so they are the retrieval query.
                    grounded, _cited, _context = ground(" ".join(selected), allow_list)
                    with st.spinner("Planning revision items..."):
                        reviewable = rv_agent.generate_reviewable(
                            grounded,
                            source_chunk_ids=_cited,
                            extracted_topics=allow_list,
                            selected_topics=list(selected),
                            session_date=session_date,
                        )
                        session = RevisionSession.model_validate(reviewable.payload)
                except NoGroundingError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Failed to generate revision items: {exc}")
                else:
                    st.success("Revision items ready (pending review)")
                    st.markdown(PENDING_BADGE)
                    st.subheader(f"Revision Session · {session.session_date}")
                    if session.notes:
                        st.caption(session.notes)
                    st.caption(
                        "Selected weak topics: " + ", ".join(session.selected_weak_topics)
                    )
                    for i, item in enumerate(session.items, start=1):
                        with st.expander(f"{i}. {item.topic} [{item.difficulty}]"):
                            if item.description:
                                st.write(item.description)
                            st.write(f"Next revision: {item.next_revision_date}")
                            if item.confidence_prompt:
                                st.caption(f"Self-check: {item.confidence_prompt}")
                    with st.expander("JSON payload"):
                        st.json(format_revision_session(session))


# ---------------------------------------------------------------------------
# Page: Batch & Benchmark (Sprint 3 demo)
# ---------------------------------------------------------------------------
elif page == "📦 Batch & Benchmark":
    st.title("📦 Batch Demo & Quality Benchmark")
    st.markdown(
        "Runs all three study-lane agents across the built-in 3-item demo "
        "dataset, then audits the outputs with the deterministic groundedness "
        "benchmark used by the AI evaluation workstream."
    )
    run = st.button("Run full batch + benchmark")
    if run:
        dataset = default_demo_dataset()
        with st.spinner("Running batch..."):
            report = run_full_batch(
                dataset, card_count=5, card_format="term-definition"
            )
            bench = benchmark_quality(
                report,
                dataset,
                expected_card_format="term-definition",
                expected_card_count=5,
            )
        st.subheader("1. Throughput summary")
        st.dataframe(report.summary())
        st.subheader("2. Quality + groundedness benchmark")
        st.json(bench.to_dict())
        st.subheader("3. Sample flashcard set (first dataset row)")
        first_fc = next(iter(report.flashcards), None)
        if first_fc is not None and first_fc.error is None:
            for i, c in enumerate(first_fc.card_set.cards[:5], start=1):
                st.write(f"**{i}.** {c.front}  →  {c.back}")
        st.caption(PENDING_BADGE)

elif page == "🧭 Mentor":
    st.title("Mentor")
    st.caption("Generate a grounded mentoring response for human review.")
    doc, chunks, is_loaded = render_current_content_status()

    if is_loaded:
        content = doc.content
        with st.form("mentor_form"):
            user_question = st.text_input("User question")
            difficulty = st.selectbox(
                "Difficulty",
                ["beginner", "intermediate", "advanced"],
                key="mentor_difficulty",
            )
            submitted = st.form_submit_button("Generate Mentor Response")

        if submitted:
            require_generation()
            try:
                # The question is the retrieval query - a literal
                # natural-language question is exactly what the retriever
                # embeds. The allow-list is the fallback query when it is blank,
                # and is pure local string processing, no model call.
                allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
                grounded, cited, context = ground(user_question, allow_list)
                with st.spinner("Generating mentor response..."):
                    reviewable = mentor_concept_service.generate_mentor_reviewable(
                        content=grounded,
                        user_question=user_question or None,
                        difficulty=difficulty,
                        context=context,
                    )
                payload = reviewable.payload
                st.warning("⚠️ Requires Human Review")
                st.write(f"Review status: **{reviewable.status.value.upper()}**")
                # The grounding heuristic is advisory, not a gate - it rejected
                # 5 of 20 correct live generations, so it flags rather than
                # blocks. Shown here and recorded on the review record.
                for warning in (reviewable.validation_report or {}).get(
                    "grounding_warnings", []
                ):
                    st.caption(f":orange[⚑ {warning}]")
                st.subheader("Explanation")
                st.write(payload.get("explanation", ""))
                st.subheader("Key points")
                for point in payload.get("key_points", []):
                    st.markdown(f"- {point}")
                st.subheader("Next steps")
                for step in payload.get("next_steps", []):
                    st.markdown(f"- {step}")
                render_provenance(
                    payload.get("references", []), cited, title=doc.title
                )
            except NoGroundingError as exc:
                st.error(str(exc))
            except ValueError as exc:
                # The agent verifies every citation against what was
                # actually retrieved. A rejection here means the model
                # cited something that does not exist - a quality gate
                # doing its job, not a crash, and it must not read as one.
                st.warning(
                    "**Output withheld by the grounding check.** "
                    f"{exc}"
                )
                st.caption(
                    "Try a more specific question, or one the uploaded "
                    "document actually covers."
                )
            except Exception as error:
                st.error(f"Error generating mentor response: {error}")

# Page: Concept Explanation
elif page == "💡 Concept Explanation":
    st.title("Concept Explanation")
    st.caption("Generate a grounded concept explanation for human review.")
    doc, chunks, is_loaded = render_current_content_status()

    if is_loaded:
        content = doc.content
        with st.form("concept_form"):
            user_question = st.text_input("Concept question")
            difficulty = st.selectbox(
                "Difficulty",
                ["beginner", "intermediate", "advanced"],
                key="concept_difficulty",
            )
            submitted = st.form_submit_button("Generate Concept Explanation")

        if submitted:
            require_generation()
            try:
                # Same wiring as the mentor page: the question is the retrieval
                # query, the allow-list is the fallback when it is blank.
                allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
                grounded, cited, context = ground(user_question, allow_list)
                with st.spinner("Generating concept explanation..."):
                    reviewable = mentor_concept_service.generate_concept_reviewable(
                        content=grounded,
                        user_question=user_question or None,
                        difficulty=difficulty,
                        context=context,
                    )
                payload = reviewable.payload
                st.warning("⚠️ Requires Human Review")
                st.write(f"Review status: **{reviewable.status.value.upper()}**")
                # The grounding heuristic is advisory, not a gate - it rejected
                # 5 of 20 correct live generations, so it flags rather than
                # blocks. Shown here and recorded on the review record.
                for warning in (reviewable.validation_report or {}).get(
                    "grounding_warnings", []
                ):
                    st.caption(f":orange[⚑ {warning}]")
                st.subheader("Definition")
                st.write(payload.get("definition", ""))
                st.subheader("Explanation")
                st.write(payload.get("explanation", ""))
                st.subheader("Key points")
                for point in payload.get("key_points", []):
                    st.markdown(f"- {point}")
                render_provenance(
                    payload.get("references", []), cited, title=doc.title
                )
            except NoGroundingError as exc:
                st.error(str(exc))
            except ValueError as exc:
                # The agent verifies every citation against what was
                # actually retrieved. A rejection here means the model
                # cited something that does not exist - a quality gate
                # doing its job, not a crash, and it must not read as one.
                st.warning(
                    "**Output withheld by the grounding check.** "
                    f"{exc}"
                )
                st.caption(
                    "Try a more specific question, or one the uploaded "
                    "document actually covers."
                )
            except Exception as error:
                st.error(f"Error generating concept explanation: {error}")

elif page == "📝 Question Bank":
    _render_question_page(
        qbank_agent,
        title="📝 Question Bank",
        caption="Generate grounded assessment questions for human review.",
        form_key="qbank_form",
    )

elif page == "🎯 Test Help":
    _render_question_page(
        test_help_agent,
        title="🎯 Test Help",
        caption="Generate grounded exam-practice questions for human review.",
        form_key="test_help_form",
    )
