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


def render_provenance(references, retrieved_ids, *, title=None) -> None:
    """Show where an answer came from, and say when it cannot be shown.

    Two problems this solves. The section used to print the raw chunk id -
    ``54f8b219-1298-46c1-8add-46d3f5020e07-c0004`` - which is a database key,
    not a citation. And it was headed "Provenance references" while nothing
    checked the ids were real: ``verify_references`` only runs when the agent
    is given a ``GroundedContext``, and these pages deliberately do not pass one
    (see the note at the call site, and issue #33). A model could invent an id
    and the page would present it as a source.

    So the label is made readable *and* checked in the same place. Doing only
    the first would be worse than the status quo: an invented citation reading
    ``Passage 5 · Physics Notes.pdf`` is far more convincing than a UUID.

    The raw id stays in an expander, because a reviewer tracing an output back
    to its chunk needs the real string, and stays untouched in the payload -
    eight consumers compare it by exact string match.

    Args:
        references: The ``references`` list from the agent payload.
        retrieved_ids: The chunk ids retrieval actually returned for this
            request.
        title: The source document's title, when known.
    """
    from src.retrieval.models import describe_chunk_id

    st.subheader("Sources")
    if not references:
        st.caption("The model cited no sources.")
        return

    known = set(retrieved_ids or [])
    for reference in references:
        segment_id = reference.get("segment_id", "")
        text = reference.get("text", "")

        if segment_id in known:
            st.markdown(f"**{describe_chunk_id(segment_id, title=title)}**")
            st.write(text)
        else:
            # Not a formatting problem: the model cited something that was not
            # retrieved, so this quote has no verified source behind it.
            st.warning(
                f"**Unverified citation** — the model cited `{segment_id}`, "
                "which was not among the passages retrieved for this question. "
                "Treat the quote below as unsourced."
            )
            st.write(text)

    with st.expander("Raw citation ids"):
        st.caption(
            "The identifiers the model returned, exactly as stored in the "
            "output payload. Used to trace an answer back to its chunk."
        )
        for reference in references:
            st.code(reference.get("segment_id", ""), language=None)
