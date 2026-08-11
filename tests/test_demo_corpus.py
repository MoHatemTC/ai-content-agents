"""Verify load_demo_corpus() against the real demo dataset.

Three things are checked:
1. Every document in DemoDataLoader.DEMO_DOCUMENTS fits into exactly ONE chunk
   under the default RetrievalConfig (chunk_size=800 chars).  This validates
   the single-chunk-per-document assumption baked into the EvalCase IDs.
2. Every expected_chunk_id in every EvalCase actually exists in the
   ChunkIndex after indexing.  This is the *canary*: if the splitter ever
   starts producing multiple chunks the IDs shift and evaluation silently
   drops to 0 recall.
3. run_benchmark() executes end-to-end over the real demo corpus and prints
   recall_at_k, mean_reciprocal_rank, and per-case retrieved_chunk_ids so
   that a human can eyeball the quality before committing.
"""

from __future__ import annotations

import textwrap
import uuid

import pytest

from src.ingestion.demo_data import DemoDataLoader
from src.retrieval.benchmark import load_demo_corpus, run_benchmark
from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex, split_text_into_chunks
from src.retrieval.retriever import ChromaRetriever

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _text_len(raw_text: str) -> int:
    """Character length of the stripped document body."""
    return len(raw_text.strip())


# ---------------------------------------------------------------------------
# 1. Single-chunk-per-document assumption
# ---------------------------------------------------------------------------


class TestDemoDocumentSizes:
    """Assert every demo document body fits in one default-sized chunk."""

    def test_all_documents_fit_in_one_chunk(self) -> None:
        config = RetrievalConfig()  # chunk_size=800 by default
        for title, content in DemoDataLoader.DEMO_DOCUMENTS:
            chunks = split_text_into_chunks(content, document_id=title, config=config)
            char_len = _text_len(content)
            assert len(chunks) == 1, (
                f"Document '{title}' produced {len(chunks)} chunks "
                f"(body length={char_len} chars, chunk_size={config.chunk_size}). "
                "The EvalCase IDs in load_demo_corpus() assume exactly one chunk "
                "(-c0000). Either increase chunk_size or update the EvalCase IDs."
            )

    def test_document_text_lengths_are_below_chunk_size(self) -> None:
        config = RetrievalConfig()
        for title, content in DemoDataLoader.DEMO_DOCUMENTS:
            char_len = _text_len(content)
            assert char_len < config.chunk_size, (
                f"Document '{title}' body is {char_len} chars which is ≥ "
                f"chunk_size={config.chunk_size}. This would trigger a window-"
                "split and break the -c0000 chunk ID assumption."
            )

    def test_chunk_ids_match_expected_pattern(self) -> None:
        """The produced IDs must match the hard-coded EvalCase IDs exactly."""
        expected_ids = {
            "Introduction-to-Python-c0000",
            "Database-Fundamentals-c0000",
            "Computer-Networks-c0000",
            "Operating-Systems-c0000",
            "Object-Oriented-Programming-c0000",
        }
        chunks, _ = load_demo_corpus()
        actual_ids = {c.chunk_id for c in chunks}
        assert expected_ids == actual_ids, (
            f"Chunk ID mismatch.\nExpected: {sorted(expected_ids)}\n"
            f"Got:      {sorted(actual_ids)}"
        )


# ---------------------------------------------------------------------------
# 2. Index membership – every expected_chunk_id is retrievable
# ---------------------------------------------------------------------------


class TestEvalCaseChunkIdsExistInIndex:
    """Guard against EvalCase IDs that refer to non-existent chunks."""

    def test_every_expected_chunk_id_is_in_the_index(self) -> None:
        chunks, cases = load_demo_corpus()

        # Use a unique collection name so parallel test runs stay isolated.
        col_name = f"demo_corpus_verify_{uuid.uuid4().hex[:8]}"
        index = ChunkIndex(
            RetrievalConfig(collection_name=col_name),
            embedding_function=None,  # defaults to HashingEmbeddingFunction
        )
        index.add_chunks(chunks)

        missing: list[tuple[str, str]] = []
        for case in cases:
            for expected_id in case.expected_chunk_ids:
                chunk = index.get_chunk(expected_id)
                if chunk is None:
                    missing.append((case.query, expected_id))

        assert not missing, (
            "The following expected_chunk_ids do not exist in the index after "
            "indexing the demo corpus.  Update load_demo_corpus() EvalCases to "
            "use the actual IDs produced by split_text_into_chunks():\n"
            + "\n".join(f"  query={q!r}  id={i!r}" for q, i in missing)
        )


# ---------------------------------------------------------------------------
# 3. End-to-end benchmark smoke test (prints quality metrics)
# ---------------------------------------------------------------------------


class TestDemoBenchmarkEndToEnd:
    """Run the full benchmark over the real demo corpus and report metrics."""

    def test_benchmark_runs_and_prints_metrics(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        col_name = f"demo_e2e_{uuid.uuid4().hex[:8]}"
        report = run_benchmark(collection_name=col_name, use_cache=True)

        # Print metrics so the developer can inspect them before committing.
        chunks, cases = load_demo_corpus()
        index = ChunkIndex(
            RetrievalConfig(collection_name=f"demo_inspect_{uuid.uuid4().hex[:8]}"),
            embedding_function=None,
        )
        index.add_chunks(chunks)
        retriever = ChromaRetriever(index)

        print("\n" + "=" * 60)
        print("DEMO CORPUS BENCHMARK RESULTS")
        print("=" * 60)
        print(f"  recall_at_k          : {report.quality.recall_at_k:.4f}")
        print(f"  mean_reciprocal_rank : {report.quality.mean_reciprocal_rank:.4f}")
        print(
            f"  mean_grounding_conf  : {report.quality.mean_grounding_confidence:.4f}"
        )
        print(f"  eval cases           : {len(cases)}")
        print(f"  corpus chunks        : {len(chunks)}")
        print("-" * 60)
        print("PER-CASE RETRIEVED CHUNK IDs (top-5):")
        for case in cases:
            results = retriever.retrieve(case.query, scope=case.scope)
            retrieved_ids = [rc.chunk.chunk_id for rc in results]
            hit = any(eid in retrieved_ids for eid in case.expected_chunk_ids)
            status = "HIT " if hit else "MISS"
            short_query = textwrap.shorten(case.query, width=45, placeholder="…")
            print(f"  [{status}] {short_query}")
            print(f"         expected : {case.expected_chunk_ids}")
            print(f"         got      : {retrieved_ids}")
        print("=" * 60)

        # Structural assertions — not quality thresholds (embedder is hashing,
        # not semantic; recall will vary but the harness must not crash).
        assert 0.0 <= report.quality.recall_at_k <= 1.0
        assert 0.0 <= report.quality.mean_reciprocal_rank <= 1.0
        assert report.indexing_latency.item_count == len(chunks)
        assert report.query_latency.item_count == len(cases)
        assert report.cache_stats is not None  # use_cache=True
