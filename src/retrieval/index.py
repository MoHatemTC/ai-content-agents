"""Incremental chunk index over ingested :class:`Chunk` records.

The index is a thin, typed wrapper around a Chroma collection: chunks are
upserted incrementally as content is ingested, re-ingesting a document
replaces its previous chunks, and the collection is the single source of
truth (no parallel in-memory state to drift).

Also provides :func:`split_text_into_chunks` — the ingestion helper that
turns raw text into :class:`Chunk` records with stable, citation-safe ids —
and :class:`HashingEmbeddingFunction`, a deterministic offline embedder.

Embedder selection is ``RETRIEVAL_EMBEDDER``: ``onnx`` (the default) is
Chroma's default embedding model - semantic matching, one-time ~80 MB
download - and ``hashing`` is the deterministic offline embedder the test
suite uses so it never touches the network. Passing an explicit
``embedding_function`` overrides both.
"""

from __future__ import annotations

import logging
import math
import os
import re
import zlib
from typing import TYPE_CHECKING, Any, cast

import chromadb
import numpy as np  # ships with chromadb (a hard dependency of it)
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings, Metadata
from chromadb.config import Settings

from src.retrieval.config import RetrievalConfig
from src.retrieval.models import Chunk
from src.ingestion.chunker import TextChunker

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from chromadb.api.types import Embeddable

    from src.retrieval.models import RetrievalScope

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Chroma rejects an upsert larger than its max batch size. The limit it
# reports is 5,461; staying below it keeps a document of any length indexable.
_MAX_UPSERT_BATCH = 5000

_ID_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_-]")


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization shared by id-free text handling."""
    return _TOKEN_RE.findall(text.lower())


def sanitize_document_id(document_id: str) -> str:
    """Replace characters unsafe for citation ids with ``-``.

    Chunk ids appear verbatim inside prompts and agent citations, so they
    must stay free of whitespace and punctuation.
    """
    return _ID_SANITIZE_RE.sub("-", document_id)



def split_text_into_chunks(
    text: str,
    *,
    document_id: str,
    session_id: str | None = None,
    config: RetrievalConfig | None = None,
) -> list[Chunk]:
    """Turn raw document text into Chunk records.

    Delegates chunking to the shared TextChunker used by the ingestion
    pipeline so retrieval and ingestion always produce identical chunk
    boundaries and stable chunk ids.

    Args:
        ...
    Returns:
        Chunk records with deterministic ids.
    """
    config = config or RetrievalConfig()
    safe_document_id = sanitize_document_id(document_id)

    chunker = TextChunker(
        chunk_size=config.chunk_size,
        overlap=config.chunk_overlap,
    )

    ingestion_chunks = chunker.chunk(
        text=text,
        document_id=safe_document_id,
        session_id=session_id,
    )

    return [
        Chunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            session_id=chunk.session_id,
            ordinal=chunk.ordinal,
            text=chunk.text,
        )
        for chunk in ingestion_chunks
    ]


class HashingEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic offline embedder: hashed bag-of-words, L2-normalized.

    Tokens are hashed (CRC32 — stable across processes, unlike ``hash()``)
    into a fixed-dimension count vector which is then L2-normalized, so
    cosine similarity rewards shared vocabulary. Not semantic — it exists so
    tests and ``RETRIEVAL_EMBEDDER=hashing`` runs are deterministic and never
    download a model — but it preserves the ranking property retrieval tests rely on:
    more shared terms means a higher score.
    """

    def __init__(self, dim: int = 256) -> None:
        """Create the embedder.

        Args:
            dim: Vector dimensionality (hash buckets).
        """
        self._dim = dim

    @staticmethod
    def name() -> str:
        """Chroma's identifier for this embedding function."""
        return "hashing-bag-of-words"

    def get_config(self) -> dict[str, Any]:
        """Serializable construction config (Chroma persistence interface)."""
        return {"dim": self._dim}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> HashingEmbeddingFunction:
        """Rebuild the embedder from :meth:`get_config` output."""
        return HashingEmbeddingFunction(dim=int(config.get("dim", 256)))

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 - Chroma's interface name
        """Embed a batch of texts.

        Args:
            input: Texts to embed (Chroma's ``EmbeddingFunction`` signature).

        Returns:
            One L2-normalized float32 vector per input text.
        """
        vectors: Embeddings = []
        for text in input:
            vector = [0.0] * self._dim
            for token in _tokenize(text):
                bucket = zlib.crc32(token.encode("utf-8")) % self._dim
                vector[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0.0:
                vector[0] = 1.0  # arbitrary unit vector: keeps cosine defined
            else:
                vector = [value / norm for value in vector]
            vectors.append(np.asarray(vector, dtype=np.float32))
        return vectors


def _default_embedding_function() -> EmbeddingFunction[Documents] | None:
    """Pick the embedder named by ``RETRIEVAL_EMBEDDER``, cached.

    ``onnx`` (the default) is Chroma's default model: semantic matching, and a
    one-time ~80 MB download. ``hashing`` is the deterministic offline embedder,
    which is what the test suite uses so it never downloads a model.

    This used to key off ``MOCK_MODE``, which conflated two unrelated ideas: a
    flag about whether agents call a real model decided which embedder indexed
    documents. Changing it silently invalidated every stored vector. The switch
    is named for what it selects now, and it is kept - unlike agent mock mode -
    because its purpose is determinism and offline CI rather than pretending to
    be a model.

    The chosen embedder is wrapped in
    :class:`~src.retrieval.performance.CachingEmbeddingFunction` so repeated
    texts are embedded once. Embedding dominates ingest cost and its rate is
    fixed, so not repeating work is the only lever available; in practice this
    serves the repeated *query* embeddings a class of students asking about the
    same few concepts produces.

    The wrapping happens here rather than at each call site on purpose. Chroma
    records the embedding function on a persisted collection and cannot rebuild
    this wrapper from its config, so a collection written with it and reopened
    without it loads but fails on query with "You must provide an embedding
    function". Deciding once, centrally, means no caller can pair them wrongly.

    Returns:
        The caching wrapper around the selected embedder.

    Raises:
        ValueError: If ``RETRIEVAL_EMBEDDER`` names something unknown. A typo
            must not silently fall back to the other embedder - that is how you
            get an index whose vectors do not match anything.
    """
    from src.retrieval.performance import CachingEmbeddingFunction

    choice = os.getenv("RETRIEVAL_EMBEDDER", "onnx").strip().lower() or "onnx"

    if choice == "hashing":
        return CachingEmbeddingFunction(HashingEmbeddingFunction())

    if choice != "onnx":
        raise ValueError(
            f"RETRIEVAL_EMBEDDER={choice!r} is not a known embedder. "
            "Use 'onnx' (Chroma's default model) or 'hashing' (offline, "
            "deterministic)."
        )

    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    logger.info("RETRIEVAL_EMBEDDER=onnx: using Chroma's default embedding model")
    return CachingEmbeddingFunction(DefaultEmbeddingFunction())


class IndexEmbedderMismatchError(RuntimeError):
    """A persisted index was written by a different embedder than the current one.

    Vectors are only comparable to others from the same model. Opening an index
    with the wrong embedder produces either a dimension error from deep inside
    Chroma or, when the dimensions happen to agree, silently meaningless
    rankings — which is worse, because nothing looks broken.
    """


def _embedder_fingerprint(embedding_function: EmbeddingFunction[Documents] | None) -> str:
    """Identify the model behind an embedder, seeing through the caching wrapper.

    ``CachingEmbeddingFunction.name()`` is ``"caching-embedding-function"``
    whichever model it wraps, so it cannot tell the offline embedder from the
    ONNX one. Its config carries ``inner_name``, which can.

    Args:
        embedding_function: The embedder about to be used, or ``None`` for
            Chroma's built-in default.

    Returns:
        A short stable identifier for the underlying model.
    """
    if embedding_function is None:
        return "chroma-default"

    try:
        config = embedding_function.get_config()
    except Exception:  # noqa: BLE001 - a custom embedder need not implement it
        config = {}

    inner = config.get("inner_name") if isinstance(config, dict) else None
    return str(inner or embedding_function.name())


class ChunkIndex:
    """Incrementally updated index of ingested chunks, backed by Chroma.

    The wrapped collection stores each chunk's text plus ``document_id`` /
    ``session_id`` / ``ordinal`` metadata, enabling scoped retrieval via
    metadata filters. All mutation methods are incremental — adding new
    content never requires rebuilding the index.
    """

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        *,
        embedding_function: EmbeddingFunction[Documents] | None = None,
    ) -> None:
        """Create (or reopen) the index.

        Args:
            config: Retrieval tunables; ``persist_directory`` selects an
                on-disk index, otherwise the index is in-memory.
            embedding_function: Explicit embedder override; when omitted the
                ``RETRIEVAL_EMBEDDER`` setting picks one (see module docstring).
        """
        self._config = config or RetrievalConfig()
        if embedding_function is None:
            embedding_function = _default_embedding_function()

        settings = Settings(anonymized_telemetry=False)
        if self._config.persist_directory is not None:
            client = chromadb.PersistentClient(
                path=self._config.persist_directory, settings=settings
            )
        else:
            client = chromadb.EphemeralClient(settings=settings)
        fingerprint = _embedder_fingerprint(embedding_function)
        try:
            self._collection = client.get_or_create_collection(
                name=self._config.collection_name,
                # Chroma's EmbeddingFunction generic is invariant, so a
                # text-only embedder needs a cast to the Documents|Images union.
                embedding_function=cast(
                    "EmbeddingFunction[Embeddable] | None", embedding_function
                ),
                metadata={"hnsw:space": "cosine", "embedder": fingerprint},
            )
        except ValueError as exc:
            # Chroma catches this itself when the embedders differ by name, and
            # says so clearly enough - it just does not say what to do about it.
            if "mbedding function" not in str(exc):
                raise
            raise IndexEmbedderMismatchError(
                f"{exc}\n\n{self._rebuild_hint()}"
            ) from exc

        self._verify_embedder(fingerprint)

    def _rebuild_hint(self) -> str:
        """The remedy, phrased for wherever the index actually lives."""
        location = self._config.persist_directory or "the in-memory index"
        return (
            f"Delete {location} and re-ingest to rebuild it with the current "
            "embedder. It is not rebuilt automatically because re-embedding a "
            "large document takes minutes, and that is not something to discard "
            "without being asked."
        )

    def _verify_embedder(self, fingerprint: str) -> None:
        """Refuse an index whose vectors came from a different model.

        Chroma performs this check itself when the embedders differ by name, but
        it cannot see through :class:`CachingEmbeddingFunction`: the wrapper
        reports ``"caching-embedding-function"`` whether it holds the offline
        embedder or the ONNX one, so Chroma sees no conflict and the mismatch
        surfaces later as ``Collection expecting embedding with dimension of
        384, got 256`` from inside a query. Worse, two models that happen to
        share a dimension would produce no error at all - just meaningless
        rankings.

        The fingerprint recorded here is of the *inner* model, which does
        distinguish them.

        A collection created before this check has no fingerprint recorded, and
        that is allowed: an existing index must survive an upgrade rather than
        be refused for lacking a field it could not have had.

        Args:
            fingerprint: Identifier of the embedder about to be used.

        Raises:
            IndexEmbedderMismatchError: If the index records a different one.
        """
        recorded = (self._collection.metadata or {}).get("embedder")
        if not recorded or recorded == fingerprint:
            return

        raise IndexEmbedderMismatchError(
            f"This index was built with the {recorded!r} embedder, but "
            f"{fingerprint!r} is in use now. Their vectors are not comparable, "
            f"so retrieval would be meaningless.\n\n{self._rebuild_hint()}"
        )

    def __len__(self) -> int:
        """Number of chunks currently indexed."""
        return self._collection.count()

    def add_chunks(self, chunks: Iterable[Chunk]) -> int:
        """Upsert chunks into the index (incremental update).

        Chunk ids are stable, so re-adding a chunk overwrites its previous
        version instead of duplicating it.

        Args:
            chunks: Chunk records to index.

        Returns:
            Number of chunks upserted.
        """
        chunk_list = list(chunks)
        if not chunk_list:
            return 0
        metadatas: list[Metadata] = []
        for chunk in chunk_list:
            metadata: dict[str, str | int | float | bool] = {
                "document_id": chunk.document_id,
                "ordinal": chunk.ordinal,
            }
            if chunk.session_id is not None:  # Chroma metadata values cannot be None
                metadata["session_id"] = chunk.session_id
            metadatas.append(metadata)
        # Chroma refuses a batch larger than its configured maximum, and a real
        # document is easily bigger: a 1,598-page textbook chunks into 8,513,
        # against a limit of 5,461. The upsert is per-batch but the ids are
        # stable, so splitting changes nothing about the result.
        for start in range(0, len(chunk_list), _MAX_UPSERT_BATCH):
            batch = chunk_list[start : start + _MAX_UPSERT_BATCH]
            self._collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                metadatas=metadatas[start : start + _MAX_UPSERT_BATCH],
            )
        logger.debug("Upserted %d chunk(s); index now holds %d", len(chunk_list), len(self))
        return len(chunk_list)

    def add_document(self, document_id: str, chunks: Sequence[Chunk]) -> int:
        """Index a document with replace semantics.

        Any previously indexed chunks of ``document_id`` are removed first,
        so re-ingesting a document never leaves stale chunks behind and
        never inflates rankings with duplicates.

        Args:
            document_id: The document the chunks belong to.
            chunks: The document's chunk records.

        Returns:
            Number of chunks indexed for the new version.

        Raises:
            ValueError: If any chunk's ``document_id`` differs from
                ``document_id``.
        """
        for chunk in chunks:
            if chunk.document_id != document_id:
                raise ValueError(
                    f"Chunk {chunk.chunk_id!r} does not belong to document {document_id!r}"
                )
        removed = self.remove_document(document_id)
        if removed:
            logger.debug("Replaced %d stale chunk(s) of document %r", removed, document_id)
        return self.add_chunks(chunks)

    def remove_document(self, document_id: str) -> int:
        """Remove every chunk of a document from the index.

        Args:
            document_id: The document to purge.

        Returns:
            Number of chunks removed (0 if the document was not indexed).
        """
        existing = self._collection.get(where={"document_id": document_id}, include=[])
        chunk_ids = existing["ids"]
        if chunk_ids:
            self._collection.delete(ids=chunk_ids)
        return len(chunk_ids)

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Fetch one chunk back from the index by id.

        Args:
            chunk_id: The chunk's stable id.

        Returns:
            The reconstructed :class:`Chunk`, or ``None`` if not indexed.
        """
        result = self._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        if not result["ids"]:
            return None
        metadata = (result["metadatas"] or [{}])[0]
        text = (result["documents"] or [""])[0]
        return Chunk(
            chunk_id=chunk_id,
            document_id=str(metadata["document_id"]),
            session_id=(
                str(metadata["session_id"]) if metadata.get("session_id") is not None else None
            ),
            ordinal=int(metadata["ordinal"]),  # type: ignore[arg-type]
            text=text,
        )

    def document_ids(self) -> list[str]:
        """List the ids of all currently indexed documents, sorted."""
        result = self._collection.get(include=["metadatas"])
        metadatas = result["metadatas"] or []
        return sorted({str(metadata["document_id"]) for metadata in metadatas})

    def query(
        self,
        text: str,
        scope: RetrievalScope,
        n_results: int,
    ) -> dict[str, Any]:
        """Run a scoped nearest-neighbour query against the collection.

        The scope's metadata filter is applied by Chroma *before* the
        similarity search, so out-of-scope chunks are never candidates.

        Args:
            text: The query text.
            scope: The document/session selection to search within.
            n_results: Maximum number of results (clamped to index size).

        Returns:
            The raw Chroma query result (ids, documents, metadatas,
            distances), with empty result lists when the index is empty.
        """
        clamped = min(n_results, len(self))
        if clamped < 1:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        return dict(
            self._collection.query(
                query_texts=[text],
                n_results=clamped,
                where=scope.to_where(),  # type: ignore[arg-type]
                include=["documents", "metadatas", "distances"],
            )
        )
