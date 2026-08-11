"""Streamlit demo pages for the Sprint 3 study lane.

Provides polished UI views for:

* Flashcards (format selector, count control, topic extraction preview).
* Study Plan (goal, difficulty sliders, hours-per-week, date range).
* Revision Assistant (weak-topic multi-select from extracted allow-list).
* Batch demo / quality benchmark view.

Every output is rendered with an explicit ``PENDING HUMAN REVIEW`` badge
reflecting the human-review gate. The UI intentionally never shows an
"export" button without first asserting the output has been approved.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Make src importable when this script is run standalone.
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from src.llm_gateway import default_model, gateway_availability
from src.study.batch import (
    default_demo_dataset,
    run_full_batch,
)
from src.study.evaluation import benchmark_quality
from src.study.flashcard_agent import FlashcardAgent
from src.study.formatters import (
    format_flashcard_set,
    format_revision_session,
    format_study_plan,
)
from src.study.revision_agent import RevisionAgent
from src.study.grounding import (
    NoGroundingError,
    ensure_document_indexed,
    grounded_content,
)
from src.study.schemas import RevisionSession, StudyPlan
from src.study.study_plan_agent import StudyPlanAgent
from src.schemas import FlashcardSet
from src.ui_common import render_current_content_status

PENDING_BADGE = ":warning: **PENDING HUMAN REVIEW — not final.**"


@st.cache_resource
def get_chunk_index():
    """The retrieval index, persisted when CHROMA_DIR is set.

    Embedding a large document costs minutes and cannot be tuned faster, so the
    only way not to pay it repeatedly is not to discard it on restart. Unset,
    the index stays in memory.
    """
    from src.retrieval import ChunkIndex, RetrievalConfig

    directory = os.getenv("CHROMA_DIR", "").strip()
    config = RetrievalConfig(persist_directory=directory) if directory else None
    return ChunkIndex(config=config)


def ensure_indexed() -> bool:
    """Embed the active document's chunks if that has not happened yet.

    Embedding dominates ingest cost and its rate is fixed, so this is lazy: the
    standalone page may be looking at a document ingested in a different
    process entirely, and re-embedding on every rerun would be unusable.

    Returns:
        Whether any indexing was performed.
    """
    doc = st.session_state.get("current_doc")
    chunks = st.session_state.get("current_chunks") or []
    if doc is None or not chunks:
        return False

    # See src/app.py: session_state is the fast path, the index is the record.
    indexed = st.session_state.setdefault("indexed_documents", set())
    if doc.id in indexed:
        return False

    index = get_chunk_index()
    if index.document_chunk_count(doc.id) == len(chunks):
        indexed.add(doc.id)
        return False

    with st.spinner(f"Preparing {len(chunks):,} passages for retrieval..."):
        performed = ensure_document_indexed(index, doc.id, chunks)
    indexed.add(doc.id)
    return performed


def ground(focus: str, topics: list[str]) -> tuple[str, list[str]]:
    """Retrieve the passages a generation should be built from.

    Args:
        focus: What the learner asked for; may be blank.
        topics: Extracted topics, used as the query when focus is blank.

    Returns:
        A ``(content, chunk_ids)`` pair for the agent call.

    Raises:
        NoGroundingError: If nothing could be retrieved.
    """
    ensure_indexed()
    doc = st.session_state.get("current_doc")

    content, cited_ids, _ = grounded_content(
        index=get_chunk_index(), document_id=doc.id, focus=focus, topics=topics
    )
    return content, cited_ids


def flashcards_page() -> None:
    st.title("🃏 Grounded Flashcard Generator")
    doc, chunks, is_loaded = render_current_content_status()

    if not is_loaded:
        return

    content = doc.content
    with st.form("fc_form"):
        col1, col2 = st.columns(2)
        with col1:
            card_format = st.radio(
                "Card format",
                ["term-definition", "qa"],
                horizontal=True,
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
        agent = FlashcardAgent()
        try:
            grounded, cited = ground(focus, allow_list)
            with st.spinner("Generating cards..."):
                # generate_reviewable, not generate: this page rendered the
                # PENDING badge below while persisting nothing, so the badge was
                # the only trace a review was ever due. app.py was fixed; this
                # entry point kept the bypass one `streamlit run` away.
                reviewable = agent.generate_reviewable(
                    grounded,
                    card_format=card_format,
                    card_count=card_count,
                    source_chunk_ids=cited,
                    extracted_topics=allow_list,
                )
                card_set = FlashcardSet.model_validate(reviewable.payload)
        except NoGroundingError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Failed to generate flashcards: {exc}")
            return

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

        with st.expander("JSON payload (vetted for export gate)"):
            st.json(format_flashcard_set(card_set))


def study_plan_page() -> None:
    st.title("📅 Grounded Study Plan")
    doc, chunks, is_loaded = render_current_content_status()

    if not is_loaded:
        return

    content = doc.content
    title = doc.title
    today = date.today()
    with st.form("sp_form"):
        col1, col2 = st.columns(2)
        with col1:
            goal = st.text_input(
                "Learner goal", f"Master the concepts in: {title}"
            )
            difficulty = st.radio(
                "Overall difficulty", ["easy", "medium", "hard"], horizontal=True
            )
            hours_per_week = st.slider(
                "Hours per week", min_value=1, max_value=30, value=10
            )
        with col2:
            start_date = st.date_input("Plan start", today)
            end_date = st.date_input(
                "Plan end", today + timedelta(days=28)
            )
            allow_list = FlashcardAgent.extract_topics(content, max_topics=30)
            st.caption(f"Planner may only schedule these {len(allow_list)} topics:")
            st.write(", ".join(allow_list) if allow_list else "(none)")
        submitted = st.form_submit_button("Generate Grounded Study Plan")

    if submitted:
        agent = StudyPlanAgent()
        try:
            # The learner goal already describes what the plan should cover,
            # so it doubles as the retrieval query.
            grounded, _cited = ground(goal, allow_list)
            with st.spinner("Building study plan..."):
                reviewable = agent.generate_reviewable(
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
            return
        except Exception as exc:
            st.error(f"Failed to build study plan: {exc}")
            return

        st.success("Study plan ready (pending review)")
        st.markdown(PENDING_BADGE)
        st.subheader(plan.goal)
        st.caption(
            f"{plan.start_date} → {plan.end_date} · difficulty={plan.overall_difficulty} · "
            f"{plan.available_hours_per_week} h/week"
        )
        st.caption(
            "Scheduled source topics: "
            + ", ".join(plan.source_topics)
        )
        for s in plan.topic_schedule:
            with st.expander(f"📌 {s.topic} ({s.difficulty})"):
                st.write(f"Dates: {s.start_date} → {s.end_date}")
                st.write(f"Duration: {s.duration_hours} hours")
                if s.resources:
                    st.caption(f"Resources: {', '.join(s.resources)}")

        with st.expander("JSON payload"):
            st.json(format_study_plan(plan))


def revision_page() -> None:
    st.title("🔄 Targeted Revision Assistant")
    doc, chunks, is_loaded = render_current_content_status()

    if not is_loaded:
        return

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
            session_date = st.date_input("Session date", date.today())
        with col2:
            st.caption("Eligible topics (from content only):")
            st.write(", ".join(allow_list))
        submitted = st.form_submit_button("Generate Revision Items")

    if submitted:
        if not selected:
            st.warning("Pick at least one topic to revise.")
            return
        agent = RevisionAgent()
        try:
            # The chosen weak topics say exactly which passages are needed.
            grounded, _cited = ground(" ".join(selected), allow_list)
            with st.spinner("Planning revision items..."):
                reviewable = agent.generate_reviewable(
                    grounded,
                    source_chunk_ids=_cited,
                    extracted_topics=allow_list,
                    selected_topics=list(selected),
                    session_date=session_date,
                )
                session = RevisionSession.model_validate(reviewable.payload)
        except NoGroundingError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Failed to generate revision items: {exc}")
            return

        st.success("Revision items ready (pending review)")
        st.markdown(PENDING_BADGE)
        st.subheader(f"Revision Session · {session.session_date}")
        if session.notes:
            st.caption(session.notes)
        st.caption(
            "Selected weak topics: "
            + ", ".join(session.selected_weak_topics)
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


def batch_demo_page() -> None:
    st.title("📦 Batch Demo & Quality Benchmark")
    st.markdown(
        "Runs all three study-lane agents across the built-in 3-item demo "
        "dataset, then audits the outputs with the deterministic groundedness "
        "benchmark used by the AI evaluation workstream."
    )
    run = st.button("Run full batch + benchmark")
    if not run:
        return

    dataset = default_demo_dataset()
    with st.spinner("Running batch..."):
        report = run_full_batch(dataset, card_count=5, card_format="term-definition")
        bench = benchmark_quality(
            report, dataset, expected_card_format="term-definition", expected_card_count=5
        )
    summary = report.summary()
    st.subheader("1. Throughput summary")
    st.dataframe(summary)

    st.subheader("2. Quality + groundedness benchmark")
    data = bench.to_dict()
    st.json(data)

    st.subheader("3. Sample flashcard set (first dataset row)")
    first_fc = next(iter(report.flashcards), None)
    if first_fc is not None and first_fc.error is None:
        for i, c in enumerate(first_fc.card_set.cards[:5], start=1):
            st.write(f"**{i}.** {c.front}  →  {c.back}")
    st.caption(PENDING_BADGE)


def main() -> None:
    st.set_page_config(page_title="Study Agents · Sprint 3", layout="wide")
    page = st.sidebar.radio(
        "Study Lane",
        [
            "🃏 Flashcards",
            "📅 Study Plan",
            "🔄 Revision Assistant",
            "📦 Batch & Benchmark",
        ],
    )
    # Say whether generation can actually happen. The app spent weeks serving
    # placeholder cards because the UI forced mock mode regardless of config
    # and nothing on screen said so. Mock mode is gone; what is left worth
    # showing is whether the gateway is reachable, and which model answers.
    available, reason = gateway_availability()
    if available:
        st.sidebar.caption(f"🟢 Live · `{default_model()}`")
    else:
        st.sidebar.error(
            f"**Generation unavailable** — {reason}. Nothing on this page can "
            "produce output until that is fixed."
        )

    if page.startswith("🃏"):
        flashcards_page()
    elif page.startswith("📅"):
        study_plan_page()
    elif page.startswith("🔄"):
        revision_page()
    else:
        batch_demo_page()


if __name__ == "__main__":
    main()
