"""Latency + quality benchmark harness for the retrieval lane.

Ties :mod:`src.retrieval.evaluation` (quality: recall@k, MRR, grounding
confidence) and :mod:`src.retrieval.performance` (caching + timing) together
into one report: how good is retrieval, and how fast, on a given corpus.

Runs fully offline against the deterministic hashing embedder by default, so
it can run in CI like the rest of the test suite. Pass a real embedder via
``embedding_function`` (e.g. Chroma's default ONNX model, with
``RETRIEVAL_EMBEDDER=onnx``) to get an honest quality read — the offline hashing
embedder is not semantic and will understate real-world recall (see the
retrieval-lane handoff doc's Task 5 for that gap).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.ingestion.demo_data import DemoDataLoader
from src.retrieval.config import RetrievalConfig
from src.retrieval.evaluation import EvalCase, EvaluationReport, evaluate_retriever
from src.retrieval.index import (
    ChunkIndex,
    HashingEmbeddingFunction,
    split_text_into_chunks,
)
from src.retrieval.models import Chunk, RetrievalScope
from src.retrieval.performance import CachingEmbeddingFunction, Timer
from src.retrieval.retriever import ChromaRetriever

if TYPE_CHECKING:
    from chromadb.api.types import Documents, EmbeddingFunction


class LatencyStats(BaseModel):
    """Timing summary for an indexing or retrieval pass, in seconds.

    Attributes:
        total_seconds: Wall-clock time for the whole pass.
        per_item_seconds: ``total_seconds`` divided by ``item_count``
            (``0.0`` when ``item_count`` is 0).
        item_count: Number of chunks indexed, or queries run.
    """

    total_seconds: float
    per_item_seconds: float
    item_count: int


class BenchmarkReport(BaseModel):
    """Full benchmark output: retrieval quality + indexing/query latency.

    Attributes:
        quality: Recall@k / MRR / grounding-confidence over the evaluation
            cases (see :mod:`src.retrieval.evaluation`).
        indexing_latency: Time to index the demo corpus.
        query_latency: Time to run every evaluation case's retrieval.
        cache_stats: Embedding-cache hit-rate stats, or ``None`` when the
            benchmark was run with ``use_cache=False``.
    """

    quality: EvaluationReport
    indexing_latency: LatencyStats
    query_latency: LatencyStats
    cache_stats: dict[str, int | float] | None = None


def load_demo_corpus(
    session_id: str | None = "demo-session",
) -> tuple[list[Chunk], list[EvalCase]]:
    """Adapter loading the real demo dataset from ``src.ingestion.demo_data``.

    Converts each demo document into :class:`Chunk` objects and builds a set of
    12 labelled :class:`EvalCase` entries whose expected chunk ids are directly
    traceable to the ingested demo content.

    Args:
        session_id: Optional session identifier for session-scoped retrieval.

    Returns:
        A tuple of ``(chunks, eval_cases)``.
    """
    chunks: list[Chunk] = []
    for title, content in DemoDataLoader.DEMO_DOCUMENTS:
        doc_chunks = split_text_into_chunks(
            content,
            document_id=title,
            session_id=session_id,
        )
        chunks.extend(doc_chunks)

    eval_cases = [
        # Introduction to Python
        EvalCase(
            query="Python programming language readability simplicity",
            scope=RetrievalScope(document_id="Introduction-to-Python"),
            expected_chunk_ids=["Introduction-to-Python-c0000"],
        ),
        EvalCase(
            query="variables store values functions loops",
            scope=RetrievalScope(document_id="Introduction-to-Python"),
            expected_chunk_ids=["Introduction-to-Python-c0000"],
        ),
        EvalCase(
            query="artificial intelligence data analysis automation",
            scope=RetrievalScope(document_id="Introduction-to-Python"),
            expected_chunk_ids=["Introduction-to-Python-c0000"],
        ),
        # Database Fundamentals
        EvalCase(
            query="relational databases tables querying SQL language",
            scope=RetrievalScope(document_id="Database-Fundamentals"),
            expected_chunk_ids=["Database-Fundamentals-c0000"],
        ),
        EvalCase(
            query="primary keys foreign keys identify records relationships",
            scope=RetrievalScope(document_id="Database-Fundamentals"),
            expected_chunk_ids=["Database-Fundamentals-c0000"],
        ),
        # Computer Networks
        EvalCase(
            query="TCP reliable communication IP packets routing",
            scope=RetrievalScope(document_id="Computer-Networks"),
            expected_chunk_ids=["Computer-Networks-c0000"],
        ),
        EvalCase(
            query="routers forward packets computer networks devices",
            scope=RetrievalScope(document_id="Computer-Networks"),
            expected_chunk_ids=["Computer-Networks-c0000"],
        ),
        # Operating Systems
        EvalCase(
            query="operating system manages processes memory hardware",
            scope=RetrievalScope(document_id="Operating-Systems"),
            expected_chunk_ids=["Operating-Systems-c0000"],
        ),
        EvalCase(
            query="file systems user interface controls hardware",
            scope=RetrievalScope(document_id="Operating-Systems"),
            expected_chunk_ids=["Operating-Systems-c0000"],
        ),
        # Object-Oriented Programming
        EvalCase(
            query="object oriented programming classes objects encapsulation",
            scope=RetrievalScope(document_id="Object-Oriented-Programming"),
            expected_chunk_ids=["Object-Oriented-Programming-c0000"],
        ),
        EvalCase(
            query="inheritance polymorphism code reuse maintainability",
            scope=RetrievalScope(document_id="Object-Oriented-Programming"),
            expected_chunk_ids=["Object-Oriented-Programming-c0000"],
        ),
        # Session scope evaluation
        EvalCase(
            query="relational tables database SQL",
            scope=RetrievalScope(session_id=session_id)
            if session_id
            else RetrievalScope(document_id="Database-Fundamentals"),
            expected_chunk_ids=["Database-Fundamentals-c0000"],
        ),
    ]

    return chunks, eval_cases


def _build_index(
    chunks: list[Chunk],
    *,
    collection_name: str,
    embedding_function: EmbeddingFunction[Documents] | None,
) -> tuple[ChunkIndex, LatencyStats]:
    """Index a corpus into a fresh :class:`ChunkIndex`, timing the whole pass."""
    index = ChunkIndex(
        RetrievalConfig(collection_name=collection_name),
        embedding_function=embedding_function,
    )
    with Timer() as timer:
        index.add_chunks(chunks)
    return index, LatencyStats(
        total_seconds=timer.elapsed_seconds,
        per_item_seconds=timer.elapsed_seconds / len(chunks) if chunks else 0.0,
        item_count=len(chunks),
    )


def run_benchmark(
    chunks: list[Chunk] | None = None,
    cases: list[EvalCase] | None = None,
    *,
    collection_name: str = "benchmark_chunks",
    use_cache: bool = True,
    embedding_function: EmbeddingFunction[Documents] | None = None,
    top_k: int | None = None,
) -> BenchmarkReport:
    """Run the full quality + latency benchmark against a corpus.

    If ``chunks`` or ``cases`` are not provided, :func:`load_demo_corpus` is
    used to default to the demo dataset from ``src.ingestion.demo_data``.

    Args:
        chunks: The corpus to index; defaults to demo dataset if omitted.
        cases: Labelled evaluation cases; defaults to demo dataset if omitted.
        collection_name: Chroma collection name for this run; pass a unique
            name (e.g. with a ``uuid4`` suffix) to isolate repeated runs.
        use_cache: Wrap the embedder in
            :class:`~src.retrieval.performance.CachingEmbeddingFunction`.
        embedding_function: Override embedder; defaults to the offline
            deterministic hashing embedder so the benchmark runs
            reproducibly and offline.
        top_k: Optional top-k override applied to every evaluation case.

    Returns:
        A report combining retrieval quality with indexing and per-query
        latency, plus cache hit-rate stats when caching is enabled.
    """
    if chunks is None or cases is None:
        demo_chunks, demo_cases = load_demo_corpus()
        if chunks is None:
            chunks = demo_chunks
        if cases is None:
            cases = demo_cases

    inner_embedder = embedding_function or HashingEmbeddingFunction()
    cache: CachingEmbeddingFunction | None = None
    active_embedder: EmbeddingFunction[Documents]
    if use_cache:
        cache = CachingEmbeddingFunction(inner_embedder)
        active_embedder = cache
    else:
        active_embedder = inner_embedder

    index, indexing_latency = _build_index(
        chunks, collection_name=collection_name, embedding_function=active_embedder
    )
    retriever = ChromaRetriever(index)

    with Timer() as query_timer:
        quality = evaluate_retriever(cases, retriever, top_k=top_k)

    query_latency = LatencyStats(
        total_seconds=query_timer.elapsed_seconds,
        per_item_seconds=query_timer.elapsed_seconds / len(cases) if cases else 0.0,
        item_count=len(cases),
    )

    return BenchmarkReport(
        quality=quality,
        indexing_latency=indexing_latency,
        query_latency=query_latency,
        cache_stats=cache.stats() if cache else None,
    )
