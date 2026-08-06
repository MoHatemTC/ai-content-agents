"""Tests for grounding the study lane in retrieved passages.

The study agents built their prompts from the whole document. That held while
the corpus was pasted notes, and broke on the first real textbook:

    ContextWindowExceededError: The input token count exceeds the maximum
    number of tokens allowed (1048576)

6.7M characters is ~1.7M tokens against a 1M limit. The retrieval lane already
existed and simply was not connected; these tests cover the connection, and the
size ceiling that stops the failure recurring however retrieval behaves.
"""

from __future__ import annotations

import pytest

from uuid import uuid4

from src.retrieval import ChunkIndex, HashingEmbeddingFunction, RetrievalConfig
from src.study.grounding import (
    MAX_CONTENT_CHARS,
    NoGroundingError,
    build_query,
    grounded_content,
    index_chunks,
)

DOC = "physics-doc"


class _IngestionChunk:
    """Shaped like an ingestion chunk, which is what the pages hold."""

    def __init__(self, index: int, text: str) -> None:
        self.id = f"{DOC}-c{index:04d}"
        self.document_id = DOC
        self.text = text
        self.ordinal = index
        self.session_id = None


def _fresh_index() -> ChunkIndex:
    """A private collection per test.

    Chroma's EphemeralClient is shared per process, so a fixed collection name
    lets one test see another's chunks - which is how an off-by-one in a batch
    count turned out to be leakage rather than a bug.
    """
    return ChunkIndex(
        config=RetrievalConfig(collection_name=f"test-{uuid4().hex[:8]}"),
        embedding_function=HashingEmbeddingFunction(),
    )


def _index_with(texts: list[str]) -> ChunkIndex:
    """An index populated offline, so no test needs a model download."""
    index = _fresh_index()
    index_chunks(index, DOC, [_IngestionChunk(i, t) for i, t in enumerate(texts)])
    return index


PASSAGES = [
    "Conduction moves energy through a material by direct molecular contact.",
    "Convection carries heat in the bulk motion of a fluid such as air or water.",
    "Radiation needs no medium: energy crosses a vacuum as electromagnetic waves.",
    "Thermal conductivity k measures how readily a material conducts heat.",
    "Newton's second law relates the net force on a body to its acceleration.",
    "Kepler's laws describe the orbits of planets around the sun.",
]


# --------------------------------------------------------------------------- #
# The query
# --------------------------------------------------------------------------- #


def test_a_typed_focus_is_the_query() -> None:
    assert build_query("thermal conduction", ["energy", "force"]) == "thermal conduction"


def test_a_blank_focus_falls_back_to_the_topics() -> None:
    """"Make 25 flashcards" is not a query, so the document's own topics stand in.

    Degrading to the document's main topics is defensible; degrading to its
    first N characters would silently confine every card to chapter one.
    """
    query = build_query("   ", ["energy", "force", "charge"])

    assert "energy" in query and "force" in query


def test_a_blank_focus_with_no_topics_still_yields_a_query() -> None:
    assert build_query("", []).strip()


# --------------------------------------------------------------------------- #
# Retrieval replaces the whole document
# --------------------------------------------------------------------------- #


def test_retrieval_returns_passages_and_their_ids() -> None:
    content, cited, context = grounded_content(
        index=_index_with(PASSAGES), document_id=DOC, focus="heat", topics=[], top_k=3
    )

    assert content.strip()
    assert cited
    assert len(cited) <= 3
    assert context.is_sufficient


def test_the_prompt_is_far_smaller_than_the_document() -> None:
    """The point of the change: a bounded prompt regardless of document size."""
    document = PASSAGES * 400  # ~28k words, well past a small model's window
    content, _cited, _ctx = grounded_content(
        index=_index_with(document), document_id=DOC, focus="conduction", topics=[]
    )

    assert len(content) < len("".join(document)) / 10


def test_content_is_capped_even_if_retrieval_returns_a_lot() -> None:
    """The bug was an unbounded prompt, so the fix must not trust retrieval."""
    huge = ["conduction " * 400 for _ in range(40)]
    content, _cited, _ctx = grounded_content(
        index=_index_with(huge), document_id=DOC, focus="conduction", topics=[], top_k=40
    )

    assert len(content) <= MAX_CONTENT_CHARS


def test_trimming_never_leaves_half_a_passage() -> None:
    """A card citing a truncated passage would misrepresent its source."""
    huge = [f"passage{i} " + "conduction " * 400 for i in range(40)]
    content, _cited, context = grounded_content(
        index=_index_with(huge), document_id=DOC, focus="conduction", topics=[], top_k=40
    )

    # Every passage that survived the trim must be byte-identical to one the
    # retriever returned. Cutting at a character offset would leave a final
    # block that is a *prefix* of a real passage - still carrying its id, so it
    # looks like a citation, while quoting text the source does not end with.
    untrimmed = set(context.as_prompt_content().split("\n\n"))
    blocks = content.split("\n\n")

    assert len(blocks) > 1, "not enough passages to have trimmed anything"
    assert len(blocks) < len(untrimmed), "nothing was actually trimmed"
    for block in blocks:
        assert block in untrimmed, f"passage cut mid-way: ...{block[-50:]!r}"


def test_an_unindexed_document_fails_loudly() -> None:
    """Better to refuse than to generate ungrounded content from a grounded tool."""
    empty = _fresh_index()

    with pytest.raises(NoGroundingError, match="Nothing could be retrieved"):
        grounded_content(index=empty, document_id=DOC, focus="heat", topics=[])


def test_retrieval_stays_inside_the_document() -> None:
    """Scope is per document; cards must never quote someone else's upload."""
    index = _index_with(PASSAGES)
    index_chunks(
        index,
        "other-doc",
        [type("C", (), {"id": "other-doc-c0000", "document_id": "other-doc",
                        "text": "Conduction in another document entirely.",
                        "ordinal": 0, "session_id": None})()],
    )

    _content, cited, _ctx = grounded_content(
        index=index, document_id=DOC, focus="conduction", topics=[], top_k=6
    )

    assert all(chunk_id.startswith(DOC) for chunk_id in cited), cited


# --------------------------------------------------------------------------- #
# Indexing a real document
# --------------------------------------------------------------------------- #


def test_indexing_splits_batches_chroma_would_reject(monkeypatch) -> None:
    """Chroma refuses an upsert larger than its maximum batch size.

    A 1,598-page textbook chunks into 8,513 against a limit of 5,461, so
    indexing a real document failed outright with
    ``Batch size of 8513 is greater than max batch size of 5461``.
    """
    import src.retrieval.index as index_module

    monkeypatch.setattr(index_module, "_MAX_UPSERT_BATCH", 10)
    index = _fresh_index()

    calls: list[int] = []
    original = index._collection.upsert

    def counting_upsert(**kwargs):
        calls.append(len(kwargs["ids"]))
        return original(**kwargs)

    monkeypatch.setattr(index._collection, "upsert", counting_upsert)

    n = index_chunks(index, DOC, [_IngestionChunk(i, f"passage {i}") for i in range(35)])

    assert n == 35
    assert len(calls) == 4, f"expected 4 batches of <=10, got {calls}"
    assert max(calls) <= 10
    assert len(index) == 35


def test_indexing_an_empty_document_is_not_an_error() -> None:
    index = _fresh_index()

    assert index_chunks(index, DOC, []) == 0


# --------------------------------------------------------------------------- #
# Indexing cost: paid once, not on every restart
# --------------------------------------------------------------------------- #


def test_a_persisted_index_survives_being_reopened(tmp_path) -> None:
    """Embedding is ~95% of ingest cost and its rate cannot be tuned.

    Measured on a 1,598-page textbook: 114.6s of 121.2s total. The only way not
    to pay that repeatedly is not to discard it, and without a persist directory
    Chroma runs in memory, so every restart re-embedded everything.

    Reopening must find the chunks *and* still answer queries - a collection
    that loads but cannot embed a query is the failure mode this guards.
    """
    config = RetrievalConfig(
        persist_directory=str(tmp_path / "chroma"),
        collection_name=f"persist-{uuid4().hex[:8]}",
    )
    chunks = [_IngestionChunk(i, t) for i, t in enumerate(PASSAGES)]

    first = ChunkIndex(config=config, embedding_function=HashingEmbeddingFunction())
    index_chunks(first, DOC, chunks)
    del first

    reopened = ChunkIndex(config=config, embedding_function=HashingEmbeddingFunction())
    assert len(reopened) == len(PASSAGES)

    _content, cited, _ctx = grounded_content(
        index=reopened, document_id=DOC, focus="conduction", topics=[], top_k=2
    )
    assert cited


def test_the_cached_embedder_can_be_rebuilt_from_its_stored_config() -> None:
    """Chroma stores the embedding function against a persisted collection.

    It reports the wrapper by name and rebuilds it from ``get_config()`` when
    nothing is passed in. A config that omits the embedder being wrapped
    produces a collection that loads fine and then fails every query with "You
    must provide an embedding function", so the round trip has to carry it.

    ``ChunkIndex`` currently always supplies an embedder itself, so Chroma does
    not exercise this path today — which is exactly why it needs testing
    directly rather than through the index, where it would pass either way.
    """
    from src.retrieval.performance import CachingEmbeddingFunction

    original = CachingEmbeddingFunction(HashingEmbeddingFunction(dim=128))
    rebuilt = CachingEmbeddingFunction.build_from_config(original.get_config())

    assert rebuilt.name() == original.name()
    # Same inner embedder, same dimensionality: a rebuilt embedder that differs
    # produces vectors incompatible with the ones already in the collection.
    assert rebuilt(["conduction"])[0].shape == original(["conduction"])[0].shape
    assert list(rebuilt(["conduction"])[0]) == list(original(["conduction"])[0])


def test_the_default_embedder_caches_repeated_text() -> None:
    """A class of students asks about the same few concepts.

    Repeated query text should be embedded once. This also pins the wrapper in
    place: without it, every identical query pays full embedding cost again.
    """
    from src.retrieval.index import _default_embedding_function

    embedder = _default_embedding_function()
    assert hasattr(embedder, "stats"), "the default embedder is no longer cached"

    embedder(["thermal conduction"])
    embedder(["thermal conduction"])

    assert embedder.stats()["hits"] >= 1
