"""Give the study agents retrieved passages instead of whole documents.

The study lane built its prompts from ``document.content`` — the entire text,
however long. That worked while the corpus was pasted notes and slide decks, and
stopped the moment a real textbook arrived:

    ContextWindowExceededError: The input token count exceeds the maximum
    number of tokens allowed (1048576)

A 1,598-page book is ~6.7M characters, roughly 1.7M tokens against a 1M limit.
Truncating would have "fixed" it while quietly restricting every card to chapter
one, which is worse than failing.

The parts needed to do it properly already existed and were simply not connected:
ingestion chunks a document, :class:`~src.retrieval.index.ChunkIndex` embeds the
chunks, and :func:`~src.retrieval.grounding.build_grounded_context` ranks them
for a query. The study agents never called any of it — they passed
``source_chunk_ids`` for provenance while citing passages they had not read
from. This module connects the two.

**Retrieval needs a query, and "make 25 flashcards" is not one.** The pages now
ask what the material should cover; when that is left blank the extracted topics
stand in, so the behaviour degrades to "the most characteristic passages of this
document" rather than to an arbitrary prefix.
"""

from __future__ import annotations

import logging

from src.retrieval import (
    ChromaRetriever,
    ChunkIndex,
    GroundedContext,
    RetrievalScope,
    build_grounded_context,
)

logger = logging.getLogger(__name__)

# Passages per generation. Enough for a model to write varied cards from, small
# enough that the prompt stays far below any provider's context window.
#
# 8 left most of the allowance unused: measured against a real textbook it
# returned ~15.7K characters against the 24K ceiling below, so a third of the
# grounding the prompt was already willing to carry was simply not fetched.
# That shows up as thin answers on the mentor and concept pages, which have
# only these passages to reason from. 12 fills it (~23K) and MAX_CONTENT_CHARS
# still trims anything unusual.
#
# This is shared by every page, so it is input cost on every generation -
# roughly +2K tokens per call. Input is the cheap half, and ungrounded output
# is the expensive kind of wrong.
DEFAULT_TOP_K = 12

# Hard ceiling on the content block, whatever retrieval returns. The bug this
# module exists to fix was an unbounded prompt, so the fix should not depend on
# retrieval always being well behaved.
MAX_CONTENT_CHARS = 24_000


class NoGroundingError(RuntimeError):
    """Raised when nothing could be retrieved for a document."""


def index_chunks(index: ChunkIndex, document_id: str, chunks) -> int:
    """Index a document's ingestion chunks so they can be retrieved.

    Args:
        index: The retrieval index to populate.
        document_id: The document the chunks belong to.
        chunks: Ingestion chunk records, as stored by the upload pages.

    Returns:
        How many chunks were indexed.
    """
    from src.validation.integration import to_retrieval_chunks

    retrieval_chunks = to_retrieval_chunks(chunks)
    if not retrieval_chunks:
        logger.warning("document %s produced no indexable chunks", document_id)
        return 0

    index.add_document(document_id, retrieval_chunks)
    return len(retrieval_chunks)


def ensure_document_indexed(index: ChunkIndex, document_id: str, chunks) -> bool:
    """Index ``document_id`` unless the index already holds exactly these chunks.

    **The persisted index was being thrown away.** With ``CHROMA_DIR`` set the
    vectors survive a restart, but both callers decided "already indexed" from
    ``st.session_state``, which is empty in every new session. They then called
    :func:`index_chunks`, and ``ChunkIndex.add_document`` has replace semantics -
    delete, re-add, re-embed. Measured on an 861-chunk textbook: 65 seconds of
    embedding per fresh session, to arrive back where it started.

    The count is the guard rather than mere presence. A document re-chunked by a
    changed chunker keeps its id but has a different number of chunks, and
    silently serving vectors built by the old chunker would be worse than
    re-embedding.

    This lives here, and not in either page, because there were two copies of
    the decision with the same bug in both - which is the duplication that
    produced BUG-08/09 and cost a PR to undo.

    Args:
        index: The retrieval index.
        document_id: The document to check.
        chunks: Ingestion chunk records the page is holding.

    Returns:
        Whether indexing was actually performed.
    """
    if not chunks:
        return False

    indexed = index.document_chunk_count(document_id)
    if indexed == len(chunks):
        logger.debug(
            "document %s already holds %d chunks; skipping embedding",
            document_id,
            indexed,
        )
        return False

    if indexed:
        logger.info(
            "document %s has %d indexed chunks but %d were supplied; rebuilding",
            document_id,
            indexed,
            len(chunks),
        )

    index_chunks(index, document_id, chunks)
    return True


def build_query(focus: str, topics: list[str], limit: int = 8) -> str:
    """Turn the user's focus, or the document's topics, into a retrieval query.

    Args:
        focus: What the learner asked the material to cover; may be blank.
        topics: The extracted topic allow-list, used when it is.
        limit: How many topics to fall back on.

    Returns:
        A non-empty query string.
    """
    if focus and focus.strip():
        return focus.strip()
    return " ".join(topics[:limit]) if topics else "key concepts"


def grounded_content(
    *,
    index: ChunkIndex,
    document_id: str,
    focus: str,
    topics: list[str],
    top_k: int = DEFAULT_TOP_K,
) -> tuple[str, list[str], GroundedContext]:
    """Retrieve the passages a generation should be built from.

    Args:
        index: The populated retrieval index.
        document_id: Scope; retrieval never crosses into another document.
        focus: The learner's focus, possibly blank.
        topics: Extracted topics, used as the query when ``focus`` is blank.
        top_k: How many passages to retrieve.

    Returns:
        A ``(content, chunk_ids, context)`` triple. ``content`` is the prompt
        block, capped at :data:`MAX_CONTENT_CHARS`; ``chunk_ids`` is the
        provenance to record on the output.

    Raises:
        NoGroundingError: If the document has nothing indexed, or nothing in it
            matched. Failing here is deliberate: an ungrounded generation from a
            grounding-first tool is the outcome worth preventing.
    """
    query = build_query(focus, topics)
    scope = RetrievalScope(document_id=document_id)

    context = build_grounded_context(query, scope, ChromaRetriever(index), top_k=top_k)

    if not context.is_sufficient:
        raise NoGroundingError(
            f"Nothing could be retrieved from this document for {query!r}. "
            "Re-upload it if it was ingested before retrieval was wired in, or "
            "try a different focus."
        )

    content = context.as_prompt_content()
    if len(content) > MAX_CONTENT_CHARS:
        # Trim on a passage boundary so a chunk is never half-quoted; a card
        # citing a truncated passage would misrepresent the source.
        kept: list[str] = []
        budget = MAX_CONTENT_CHARS
        for block in content.split("\n\n"):
            if len(block) + 2 > budget:
                break
            kept.append(block)
            budget -= len(block) + 2
        content = "\n\n".join(kept) or content[:MAX_CONTENT_CHARS]
        logger.info("trimmed grounded content to %d chars", len(content))

    logger.info(
        "grounded generation: document=%s query=%r chunks=%d chars=%d",
        document_id,
        query,
        len(context.chunk_ids),
        len(content),
    )
    return content, list(context.chunk_ids), context
