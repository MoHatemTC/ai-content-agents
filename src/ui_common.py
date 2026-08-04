"""Session-state helpers shared by every Streamlit entry point.

The app has three ways in — ``src/app.py`` (the combined router),
``src/ingestion/ui.py`` and ``src/study/ui.py`` — and the study pages exist
twice, once in the router and once standalone. When the "which document am I
working on?" logic lived in both copies, a fix applied to one silently missed
the other: the flashcard page in ``app.py`` was corrected to pass chunk *ids*
while its twin in ``study/ui.py`` kept passing ``Chunk`` records, and every
generation from uploaded content raised a ``ValidationError`` per chunk.

Both copies now call the same two functions from here, so the pages cannot
disagree about the active document again.

The active content lives in two session-state keys, written by every ingestion
path (single upload, paste, batch, Content Library, demo dataset):

``current_doc``
    The full :class:`~src.ingestion.schema.Document`, content included.
``current_chunks``
    Its :class:`~src.ingestion.schema.Chunk` records, in order.

This module is deliberately at the top level rather than inside a lane:
``src.study`` does not otherwise depend on ``src.ingestion``, and adding that
edge to import a shared widget would be the wrong shape.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from src.ingestion.schema import Chunk, Document


def render_current_content_status() -> tuple[Document | None, list[Chunk], bool]:
    """Draw the "Current Content" header and report what is active.

    Pages call this first and return early when nothing is loaded. There is no
    built-in sample fallback: a page that quietly generated from a phantom
    document while the user believed they were working from their own upload is
    exactly the confusion this replaces.

    Returns:
        A ``(document, chunks, is_loaded)`` tuple. When nothing is loaded this
        is ``(None, [], False)`` and a prompt pointing at the Upload page has
        been rendered; the caller should stop. Otherwise ``is_loaded`` is
        ``True`` and the header has been drawn.
    """
    doc = st.session_state.get("current_doc")
    chunks = list(st.session_state.get("current_chunks") or [])

    if doc is None or not getattr(doc, "content", None):
        st.warning("⚠️ Please upload educational content first.")
        st.info(
            "💡 Go to the **Upload Content** page to upload a file, paste text, "
            "or select a document from the Content Library."
        )
        return None, [], False

    title = getattr(doc, "title", "Uploaded content")

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### 📄 Current Content: **{title}**")
        with col2:
            st.markdown(f"**🧩 {len(chunks)} Chunks Loaded**")

    return doc, chunks, True


def chunk_ids(chunks: Sequence[Chunk]) -> list[str]:
    """Reduce stored chunk records to the id strings the agents accept.

    ``session_state["current_chunks"]`` holds ``Chunk`` objects, but every
    agent's ``source_chunk_ids`` field is ``list[str]``. Forwarding the records
    straight through is the defect this exists to prevent.

    Args:
        chunks: Chunk records as stored by the ingestion pages.

    Returns:
        Their ``id`` values, in order.
    """
    return [chunk.id for chunk in chunks]
