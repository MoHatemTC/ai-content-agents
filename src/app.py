
from __future__ import annotations

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
from src.registry import AgentRegistry
from src.generation import MockGenerator
from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_flashcard_set,
    format_revision_session,
    format_study_plan,
)
from src.study.revision_agent import RevisionAgent
from src.study.study_plan_agent import StudyPlanAgent

# ---------------------------------------------------------------------------
# Initialize shared services
# ---------------------------------------------------------------------------
@st.cache_resource
def get_loader():
    return ContentLoader()

@st.cache_resource
def get_registry():
    return AgentRegistry()

@st.cache_resource
def get_generator():
    return MockGenerator(get_registry())

@st.cache_resource
def get_flashcard_agent():
    return FlashcardAgent(mock_mode=True)

@st.cache_resource
def get_study_plan_agent():
    return StudyPlanAgent(mock_mode=True)

@st.cache_resource
def get_revision_agent():
    return RevisionAgent(mock_mode=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PENDING_BADGE = ":warning: **PENDING HUMAN REVIEW — not final.**"


def _get_doc():
    doc = st.session_state.get("current_doc")
    if doc is None:
        fallback = (
            "Python Programming Basics. "
            "Python is a high-level, interpreted programming language. "
            "Key concepts include Functions, Loops (for and while), Classes, "
            "Lists, Dictionaries, and Error Handling. Functions are reusable "
            "blocks defined with the def keyword. Loops iterate over sequences. "
            "Classes enable object-oriented programming. "
            "Lists and Dictionaries are core data structures. "
            "Error Handling uses try/except blocks."
        )
        return "Built-in sample (Python Programming)", fallback
    title = getattr(doc, "title", "Uploaded content")
    content = getattr(doc, "content", "") or ""
    return title, content


# ---------------------------------------------------------------------------
# Page config + sidebar nav
# ---------------------------------------------------------------------------
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
    ],
)

loader = get_loader()
registry = get_registry()
generator = get_generator()
fc_agent = get_flashcard_agent()
sp_agent = get_study_plan_agent()
rv_agent = get_revision_agent()


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

    tab1, tab2 = st.tabs(["📁 Upload File", "📝 Paste Text"])

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
                with st.spinner("Processing text..."):
                    doc = loader.load_text(pasted_text, title)
                    chunks = loader.store.get_chunks_by_document_id(doc.id)
                    st.success(f"Successfully processed {doc.title}!")
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
                st.error(f"Error processing text: {str(e)}")


# ---------------------------------------------------------------------------
# Page: Flashcards (Sprint 3 polished agent)
# ---------------------------------------------------------------------------
elif page == "🃏 Generate Flashcards":
    st.title("🃏 Grounded Flashcard Generator")
    title, content = _get_doc()
    st.caption(f"Content source: {title}")
    if "current_doc" not in st.session_state:
        st.info("Tip: upload content on Upload Content page, or use the built-in sample.")

    with st.form("fc_form"):
        col1, col2 = st.columns(2)
        with col1:
            card_format = st.radio(
                "Card format", ["term-definition", "qa"], horizontal=True,
                help="term-definition: front = term. Q-A: front = a question.",
            )
            card_count = st.slider("Card count", min_value=1, max_value=25, value=8)
        with col2:
            allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
            st.caption(f"Extracted topic allow-list ({len(allow_list)} topics):")
            st.write(", ".join(allow_list) if allow_list else "(none)")
        submitted = st.form_submit_button("Generate Grounded Flashcards")

    if submitted:
        try:
            chunk_ids = list(st.session_state.get("current_chunks", []) or [])
            with st.spinner("Generating cards..."):
                card_set = fc_agent.generate(
                    content,
                    card_format=card_format,
                    card_count=card_count,
                    source_chunk_ids=chunk_ids,
                )
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
    title, content = _get_doc()
    st.caption(f"Content source: {title}")
    from datetime import date as _date

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
        try:
            with st.spinner("Building study plan..."):
                plan = sp_agent.generate(
                    content,
                    learner_goal=goal,
                    difficulty=difficulty,
                    start_date=start_date,
                    end_date=end_date,
                    hours_per_week=float(hours_per_week),
                )
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
    title, content = _get_doc()
    st.caption(f"Content source: {title}")
    from datetime import date as _date

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
            try:
                with st.spinner("Planning revision items..."):
                    session = rv_agent.generate(
                        content,
                        selected_topics=list(selected),
                        session_date=session_date,
                    )
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
