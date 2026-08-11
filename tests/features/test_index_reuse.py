"""A persisted index is reused, not rebuilt.

With ``CHROMA_DIR`` set the vectors survive a restart. Both upload paths still
re-embedded on every fresh session, because they decided "already indexed" from
``st.session_state`` - which is empty in a new session - and then called
``ChunkIndex.add_document``, whose semantics are *replace*: delete, re-add,
re-embed.

Measured on the 861-chunk textbook in use here: 76 ms per chunk, so **65
seconds of embedding per session** to arrive back at vectors already on disk.
Embedding is ~97% of ingest cost and its rate cannot be tuned, so this was the
most expensive avoidable thing the app did.
"""

from __future__ import annotations

from uuid import uuid4

from src.ingestion.schema import Chunk as IngestionChunk
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex, HashingEmbeddingFunction
from src.retrieval.models import Chunk
from src.study.grounding import ensure_document_indexed


def make_index() -> ChunkIndex:
    """An isolated in-memory index; the hashing embedder never downloads."""
    config = RetrievalConfig(collection_name=f"test-{uuid4().hex}")  # type: ignore[arg-type]
    return ChunkIndex(config, embedding_function=HashingEmbeddingFunction())


def retrieval_chunks(document_id: str, count: int) -> list[Chunk]:
    """What ChunkIndex.add_document takes."""
    return [
        Chunk(
            chunk_id=f"{document_id}-c{i:04d}",
            document_id=document_id,
            ordinal=i,
            text=f"Passage {i} about vector spaces and linear independence.",
        )
        for i in range(count)
    ]


def page_chunks(document_id: str, count: int) -> list[IngestionChunk]:
    """What the upload pages actually hold in session_state.

    ensure_document_indexed takes these and converts, which is why the tests
    below use them rather than the retrieval shape - passing the wrong kind is
    a mistake a caller could really make.
    """
    return [
        IngestionChunk(
            id=f"{document_id}-c{i:04d}",
            document_id=document_id,
            ordinal=i,
            text=f"Passage {i} about vector spaces and linear independence.",
        )
        for i in range(count)
    ]


class CountingIndex(ChunkIndex):
    """Records how often chunks were actually written, i.e. embedded."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_document_calls = 0

    def add_document(self, document_id, chunks):  # type: ignore[override]
        self.add_document_calls += 1
        return super().add_document(document_id, chunks)


def counting_index() -> CountingIndex:
    config = RetrievalConfig(collection_name=f"test-{uuid4().hex}")  # type: ignore[arg-type]
    return CountingIndex(config, embedding_function=HashingEmbeddingFunction())


# --------------------------------------------------------------------------- #
# The count itself
# --------------------------------------------------------------------------- #


def test_an_unindexed_document_counts_zero() -> None:
    assert make_index().document_chunk_count("never-seen") == 0


def test_the_count_matches_what_was_indexed() -> None:
    index = make_index()
    index.add_document("doc-a", retrieval_chunks("doc-a", 7))

    assert index.document_chunk_count("doc-a") == 7


def test_the_count_is_per_document() -> None:
    """A shared collection holds several documents; the count must not blur them."""
    index = make_index()
    index.add_document("doc-a", retrieval_chunks("doc-a", 3))
    index.add_document("doc-b", retrieval_chunks("doc-b", 5))

    assert index.document_chunk_count("doc-a") == 3
    assert index.document_chunk_count("doc-b") == 5


# --------------------------------------------------------------------------- #
# The decision
# --------------------------------------------------------------------------- #


def test_a_new_document_is_indexed() -> None:
    index = counting_index()

    assert ensure_document_indexed(index, "doc-a", page_chunks("doc-a", 4)) is True
    assert index.add_document_calls == 1


def test_an_already_indexed_document_is_not_re_embedded() -> None:
    """The 65 seconds. Nothing is written the second time round."""
    index = counting_index()
    chunks = page_chunks("doc-a", 4)
    ensure_document_indexed(index, "doc-a", chunks)

    performed = ensure_document_indexed(index, "doc-a", chunks)

    assert performed is False
    assert index.add_document_calls == 1, "the document was embedded twice"


def test_a_rechunked_document_is_rebuilt() -> None:
    """Presence alone is not enough.

    A chunker change keeps the document id and alters the chunk count. Serving
    vectors built by the old chunker would be quietly wrong, so the count -
    not mere presence - is the guard.
    """
    index = counting_index()
    ensure_document_indexed(index, "doc-a", page_chunks("doc-a", 4))

    performed = ensure_document_indexed(index, "doc-a", page_chunks("doc-a", 9))

    assert performed is True
    assert index.add_document_calls == 2
    assert index.document_chunk_count("doc-a") == 9


def test_no_chunks_is_not_an_index_operation() -> None:
    index = counting_index()

    assert ensure_document_indexed(index, "doc-a", []) is False
    assert index.add_document_calls == 0


def test_reuse_survives_a_fresh_index_object() -> None:
    """The real scenario: a new session opens the same persisted collection.

    A new ChunkIndex over the same collection is what a restarted app has, and
    it must see the existing vectors rather than start from nothing.
    """
    config = RetrievalConfig(collection_name=f"test-{uuid4().hex}")  # type: ignore[arg-type]
    first = CountingIndex(config, embedding_function=HashingEmbeddingFunction())
    chunks = page_chunks("doc-a", 6)
    ensure_document_indexed(first, "doc-a", chunks)

    second = CountingIndex(config, embedding_function=HashingEmbeddingFunction())
    performed = ensure_document_indexed(second, "doc-a", chunks)

    assert performed is False
    assert second.add_document_calls == 0, "a new session re-embedded the document"
