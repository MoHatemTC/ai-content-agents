"""Incremental chunk index over ingested :class:`Chunk` records.

The index is a thin, typed wrapper around a Chroma collection: chunks are
upserted incrementally as content is ingested, re-ingesting a document
replaces its previous chunks, and the collection is the single source of
truth (no parallel in-memory state to drift).

Also provides :func:`split_text_into_chunks` — the ingestion helper that
turns raw text into :class:`Chunk` records with stable, citation-safe ids —
and :class:`HashingEmbeddingFunction`, a deterministic offline embedder.

Embedder selection mirrors the repo's ``MOCK_MODE`` convention: when
``MOCK_MODE=true`` (the team default) the offline hashing embedder is used,
so fresh clones and the test suite never touch the network; setting
``MOCK_MODE=false`` opts into Chroma's default ONNX embedding model
(one-time ~80 MB download, semantic matching). Passing an explicit
``embedding_function`` always overrides both.
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

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from chromadb.api.types import Embeddable

    from src.retrieval.models import RetrievalScope

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
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


def _window_split(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one oversized paragraph into word windows with overlap.

    Windows never cut words; a window may slightly exceed ``chunk_size``
    when a single word is longer than the budget (progress is guaranteed).
    """
    words = paragraph.split()
    pieces: list[str] = []
    current: list[str] = []
    seed_count = 0  # trailing words carried over from the previous window

    def joined_len(items: list[str]) -> int:
        return sum(len(word) for word in items) + max(len(items) - 1, 0)

    for word in words:
        overflows = joined_len([*current, word]) > chunk_size
        if overflows and len(current) > seed_count:
            pieces.append(" ".join(current))
            tail: list[str] = []
            for previous in reversed(current):
                if joined_len([previous, *tail]) > overlap:
                    break
                tail.insert(0, previous)
            current = list(tail)
            seed_count = len(tail)
        current.append(word)
    if len(current) > seed_count:
        pieces.append(" ".join(current))
    return pieces


def split_text_into_chunks(
    text: str,
    *,
    document_id: str,
    session_id: str | None = None,
    config: RetrievalConfig | None = None,
) -> list[Chunk]:
    """Turn raw document text into :class:`Chunk` records.

    Paragraphs (blank-line separated) are greedily packed into chunks of up
    to ``config.chunk_size`` characters; a single oversized paragraph falls
    back to a word-window split with ``config.chunk_overlap`` characters of
    overlap between windows.

    Args:
        text: The raw document text; empty/whitespace text yields no chunks.
        document_id: Source document id; sanitized so chunk ids stay
            citation-safe (``[^A-Za-z0-9_-]`` becomes ``-``).
        session_id: Optional owning session, propagated to every chunk.
        config: Chunking tunables; defaults to :class:`RetrievalConfig`.

    Returns:
        Chunks with deterministic ids ``f"{document_id}-c{ordinal:04d}"``,
        in document order.
    """
    config = config or RetrievalConfig()
    safe_document_id = sanitize_document_id(document_id)

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    pieces: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > config.chunk_size:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            pieces.extend(_window_split(paragraph, config.chunk_size, config.chunk_overlap))
        elif not buffer:
            buffer = paragraph
        elif len(buffer) + 2 + len(paragraph) <= config.chunk_size:
            buffer = f"{buffer}\n\n{paragraph}"
        else:
            pieces.append(buffer)
            buffer = paragraph
    if buffer:
        pieces.append(buffer)

    return [
        Chunk(
            chunk_id=f"{safe_document_id}-c{ordinal:04d}",
            document_id=safe_document_id,
            session_id=session_id,
            ordinal=ordinal,
            text=piece,
        )
        for ordinal, piece in enumerate(pieces)
    ]


class HashingEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic offline embedder: hashed bag-of-words, L2-normalized.

    Tokens are hashed (CRC32 — stable across processes, unlike ``hash()``)
    into a fixed-dimension count vector which is then L2-normalized, so
    cosine similarity rewards shared vocabulary. Not semantic — it exists so
    tests and ``MOCK_MODE`` runs are deterministic and never download a
    model — but it preserves the ranking property retrieval tests rely on:
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
    """Pick the embedder per the repo's ``MOCK_MODE`` convention.

    Returns:
        The offline hashing embedder when ``MOCK_MODE`` is true (default),
        or ``None`` (Chroma's default ONNX model) when live mode is enabled.
    """
    mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true"
    if mock_mode:
        return HashingEmbeddingFunction()
    logger.info("MOCK_MODE=false: using Chroma's default embedding model")
    return None


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
                ``MOCK_MODE`` convention picks one (see module docstring).
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
        self._collection = client.get_or_create_collection(
            name=self._config.collection_name,
            # Chroma's EmbeddingFunction generic is invariant, so a text-only
            # embedder needs a cast to the Documents|Images union it accepts.
            embedding_function=cast(
                "EmbeddingFunction[Embeddable] | None", embedding_function
            ),
            metadata={"hnsw:space": "cosine"},
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
        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in chunk_list],
            documents=[chunk.text for chunk in chunk_list],
            metadatas=metadatas,
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
