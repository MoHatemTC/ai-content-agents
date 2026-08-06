"""Tests for src.retrieval.performance (embedding cache) and
src.retrieval.benchmark (quality + latency harness).

Offline and deterministic: everything runs against the hashing embedder,
same as the rest of the suite, so no network access or timing flakiness is
required for correctness assertions (only non-negativity is asserted about
elapsed time, never a specific duration).
"""

from __future__ import annotations

from uuid import uuid4

from src.retrieval.benchmark import run_benchmark
from src.retrieval.evaluation import EvalCase
from src.retrieval.index import HashingEmbeddingFunction
from src.retrieval.models import Chunk, RetrievalScope
from src.retrieval.performance import CachingEmbeddingFunction, Timer


class TestCachingEmbeddingFunction:
    def test_repeated_text_is_served_from_cache(self) -> None:
        inner = HashingEmbeddingFunction()
        cached = CachingEmbeddingFunction(inner)

        first = cached(["hello world", "goodbye world"])
        second = cached(["hello world"])  # repeat of a text already embedded

        stats = cached.stats()
        assert stats["misses"] == 2  # both distinct texts embedded once
        assert stats["hits"] == 1  # "hello world" served from cache
        assert list(first[0]) == list(second[0])

    def test_cache_output_matches_uncached_output(self) -> None:
        inner = HashingEmbeddingFunction()
        cached = CachingEmbeddingFunction(inner)
        direct = inner(["some deterministic text"])
        through_cache = cached(["some deterministic text"])
        assert list(direct[0]) == list(through_cache[0])

    def test_batch_with_mixed_hits_and_misses_preserves_order(self) -> None:
        inner = HashingEmbeddingFunction()
        cached = CachingEmbeddingFunction(inner)
        cached(["alpha", "beta"])  # warm the cache
        mixed = cached(["beta", "gamma", "alpha"])
        direct = inner(["beta", "gamma", "alpha"])
        for cached_vec, direct_vec in zip(mixed, direct):
            assert list(cached_vec) == list(direct_vec)
        stats = cached.stats()
        assert stats["hits"] == 2  # "beta" and "alpha" were already cached
        assert stats["misses"] == 3  # "alpha", "beta" (first call) + "gamma"

    def test_eviction_respects_max_entries(self) -> None:
        inner = HashingEmbeddingFunction()
        cached = CachingEmbeddingFunction(inner, max_entries=2)
        cached(["a", "b", "c"])  # 3 distinct texts, cap of 2
        stats = cached.stats()
        assert stats["cached_entries"] == 2

    def test_stats_start_at_zero(self) -> None:
        cached = CachingEmbeddingFunction(HashingEmbeddingFunction())
        assert cached.stats() == {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "cached_entries": 0,
        }

    def test_hit_rate_reflects_repeat_ratio(self) -> None:
        cached = CachingEmbeddingFunction(HashingEmbeddingFunction())
        cached(["x"])
        cached(["x"])
        cached(["x"])
        stats = cached.stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 2
        assert stats["hit_rate"] == 2 / 3


class TestTimer:
    def test_records_nonnegative_elapsed_time(self) -> None:
        with Timer() as timer:
            pass
        assert timer.elapsed_seconds >= 0.0

    def test_elapsed_time_resets_per_use(self) -> None:
        timer = Timer()
        with timer:
            pass
        first = timer.elapsed_seconds
        with timer:
            pass
        assert timer.elapsed_seconds >= 0.0
        assert isinstance(first, float)


def _demo_chunks() -> list[Chunk]:
    """A tiny three-document demo corpus spanning unrelated topics."""
    return [
        Chunk(
            chunk_id=f"demo-c{i:04d}",
            document_id="demo",
            session_id="session-1",
            ordinal=i,
            text=text,
        )
        for i, text in enumerate(
            [
                "Newton's second law states force equals mass times acceleration.",
                "Git branches are lightweight pointers to commits.",
                "Photosynthesis converts light energy into chemical energy.",
            ]
        )
    ]


def _demo_cases() -> list[EvalCase]:
    """Labelled cases matching the demo corpus above."""
    return [
        EvalCase(
            query="newton force acceleration",
            scope=RetrievalScope(document_id="demo"),
            expected_chunk_ids=["demo-c0000"],
        ),
        EvalCase(
            query="git branches commits",
            scope=RetrievalScope(document_id="demo"),
            expected_chunk_ids=["demo-c0001"],
        ),
    ]


class TestRunBenchmark:
    def test_produces_quality_and_latency_report(self) -> None:
        report = run_benchmark(
            _demo_chunks(),
            _demo_cases(),
            collection_name=f"bench-{uuid4().hex}",
        )
        assert report.quality.num_cases == 2
        assert report.indexing_latency.item_count == 3
        assert report.indexing_latency.total_seconds >= 0.0
        assert report.query_latency.item_count == 2
        assert report.query_latency.total_seconds >= 0.0
        assert report.cache_stats is not None
        assert report.cache_stats["misses"] >= 1

    def test_can_run_without_cache(self) -> None:
        report = run_benchmark(
            _demo_chunks(),
            _demo_cases(),
            collection_name=f"bench-{uuid4().hex}",
            use_cache=False,
        )
        assert report.cache_stats is None
        assert report.quality.num_cases == 2

    def test_empty_corpus_and_cases_do_not_error(self) -> None:
        report = run_benchmark(
            [],
            [],
            collection_name=f"bench-{uuid4().hex}",
        )
        assert report.indexing_latency.item_count == 0
        assert report.indexing_latency.per_item_seconds == 0.0
        assert report.query_latency.item_count == 0
        assert report.quality.num_cases == 0

    def test_top_k_override_is_passed_through(self) -> None:
        report = run_benchmark(
            _demo_chunks(),
            _demo_cases(),
            collection_name=f"bench-{uuid4().hex}",
            top_k=1,
        )
        for case_result in report.quality.case_results:
            assert len(case_result.retrieved_chunk_ids) <= 1
