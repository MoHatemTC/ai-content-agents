"""Embedding-level caching to keep retrieval latency low.

Every retrieval query and every ingested chunk gets embedded before Chroma
can search or index it. For content that repeats — the same chunk
re-ingested, the same or similar queries asked again in a session — that
embedding call is pure overhead. :class:`CachingEmbeddingFunction` wraps any
Chroma ``EmbeddingFunction`` with a bounded in-memory cache keyed on exact
text, so repeat text is embedded exactly once.

Scope note: per the sprint requirement, this targets low latency for
**small and medium** content. The cache is a plain in-process
least-recently-used dict with a hard entry cap — it resets per process and
is not a distributed cache sized for huge corpora. :func:`Timer` is a small
stopwatch helper used by :mod:`src.retrieval.benchmark` to measure the
latency this cache is meant to improve.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


def _text_key(text: str) -> str:
    """Stable, bounded-size cache key for a piece of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachingEmbeddingFunction(EmbeddingFunction[Documents]):
    """Wraps a Chroma embedding function with a bounded LRU text cache.

    Only texts not already cached are passed to the wrapped embedder, and
    only in one batched call per invocation (so a batch with 3 cached texts
    and 2 new ones costs exactly one 2-item embed call, not five 1-item
    calls). Cached vectors are returned in their original request order.
    """

    def __init__(
        self, inner: EmbeddingFunction[Documents], *, max_entries: int = 5000
    ) -> None:
        """Create the caching wrapper.

        Args:
            inner: The embedding function to cache calls to (e.g.
                ``HashingEmbeddingFunction`` or the live ONNX embedder).
            max_entries: Maximum distinct texts cached before the least
                recently used entry is evicted.
        """
        self._inner = inner
        self._max_entries = max_entries
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def name() -> str:
        """Chroma's identifier for this embedding function."""
        return "caching-embedding-function"

    def get_config(self) -> dict[str, Any]:
        """Serializable construction config (Chroma persistence interface).

        The wrapped embedder is recorded by name and config, not just the
        cache's own sizing. Chroma stores this against a persisted collection
        and rebuilds the embedder when the collection is reopened; without the
        inner details the collection loads but every query fails with "You must
        provide an embedding function". The cache contents are not serialized —
        they are a within-process optimisation and rebuild themselves.
        """
        return {
            "max_entries": self._max_entries,
            "inner_name": self._inner.name(),
            "inner_config": self._inner.get_config(),
        }

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> CachingEmbeddingFunction:
        """Rebuild the wrapper, and the embedder it wraps, from :meth:`get_config`.

        Args:
            config: Output of :meth:`get_config`.

        Returns:
            An equivalent wrapper with an empty cache.
        """
        # Imported here rather than at module scope: index.py imports this
        # module for the default embedder, so a top-level import back into it
        # would be circular.
        from src.retrieval.index import HashingEmbeddingFunction

        inner_config = config.get("inner_config") or {}
        if config.get("inner_name") == HashingEmbeddingFunction.name():
            inner: EmbeddingFunction[Documents] = (
                HashingEmbeddingFunction.build_from_config(inner_config)
            )
        else:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            inner = DefaultEmbeddingFunction()

        return CachingEmbeddingFunction(
            inner, max_entries=int(config.get("max_entries", 5000))
        )

    def __call__(self, input: Documents) -> Embeddings:
        """Embed a batch of texts, serving repeats from cache.

        Args:
            input: Texts to embed.

        Returns:
            One vector per input text, in the same order as ``input``.
        """
        vectors: list[Any] = [None] * len(input)
        misses: list[tuple[int, str, str]] = []  # (position, cache key, text)

        for position, text in enumerate(input):
            key = _text_key(text)
            if key in self._cache:
                self._cache.move_to_end(key)
                vectors[position] = self._cache[key]
                self._hits += 1
            else:
                misses.append((position, key, text))
                self._misses += 1

        if misses:
            embedded = self._inner([text for _, _, text in misses])
            for (position, key, _text), vector in zip(misses, embedded):
                vectors[position] = vector
                self._cache[key] = vector
                self._cache.move_to_end(key)
                if len(self._cache) > self._max_entries:
                    self._cache.popitem(last=False)

        return vectors

    def stats(self) -> dict[str, int | float]:
        """Cache hit-rate stats, surfaced in benchmark reports.

        Returns:
            A dict with ``hits``, ``misses``, ``hit_rate`` (0.0 when nothing
            has been embedded yet), and ``cached_entries``.
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "cached_entries": len(self._cache),
        }


class Timer:
    """A tiny context-manager stopwatch used to measure latency.

    Usage::

        with Timer() as timer:
            do_the_thing()
        print(timer.elapsed_seconds)
    """

    def __init__(self) -> None:
        """Create the timer; ``elapsed_seconds`` is ``0.0`` until the block exits."""
        self.elapsed_seconds: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> Timer:
        """Start the stopwatch."""
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop the stopwatch and record ``elapsed_seconds``."""
        self.elapsed_seconds = time.perf_counter() - self._start
