# Retrieval & Grounding — Sprint 3 Addendum

Extends the existing `src/retrieval/` lane (see `docs/retrieval-lane.md` and
`docs/retrieval-handoff.md`) — nothing here replaces or duplicates that
lane; these are four new files that build on its public contracts
(`Retriever`, `GroundedContext`, `verify_references`, `ChunkIndex`).

## What's new

| File | Purpose |
|---|---|
| `src/retrieval/verifier.py` | `GroundingVerificationRule` — wraps `verify_references()` as a `GuardrailRule` so the validation lane can *enforce*, not just check, that every cited `segment_id` was genuinely retrieved. Closes Task 3 from the handoff doc. |
| `src/retrieval/evaluation.py` | `EvalCase` / `evaluate_retriever()` — recall@k, MRR, and a per-query `grounding_confidence()` signal over a labelled `(query, scope, expected_chunk_ids)` set. Addresses Task 5 (retrieval-quality measurement). |
| `src/retrieval/performance.py` | `CachingEmbeddingFunction` — bounded LRU cache wrapping any Chroma embedder, so repeat chunk/query text is embedded once. `Timer` — a small stopwatch used for latency measurement. |
| `src/retrieval/benchmark.py` | `run_benchmark()` — ties evaluation + performance together: indexes a corpus, times ingestion and query latency, and reports quality + cache hit-rate in one `BenchmarkReport`. |

Tests: `tests/test_retrieval_grounding.py` (verifier + evaluation, 21 cases)
and `tests/test_retrieval_perf.py` (cache + benchmark, 12 cases). Both run
offline against the deterministic hashing embedder, same as the rest of the
suite — no new dependencies, no network access.

## Design notes

- **`GroundingVerificationRule` needs a `GroundedContext` the output schema
  doesn't carry.** Rather than changing `GuardrailContext` (shared with
  every other rule), the context is bound directly on the rule instance via
  `.for_context(ctx)`, called once per query right before checking that
  query's output. `ReferencesPresentRule` still owns "are there references at
  all"; this rule only owns "are the ones present real".
- **`grounding_confidence()` is deliberately a simple, conservative proxy**
  (0 with no hits, otherwise the top result's clamped cosine score) — not a
  calibrated probability. It's meant to be thresholded on, not trusted as
  ground truth.
- **The cache is sized for small/medium content**, per the sprint scope: a
  plain in-process LRU dict with a hard entry cap, not a distributed cache.
  It resets per process.
- **`run_benchmark()` takes no dependency on `src.ingestion.demo_data`.**
  Its exact shape wasn't available to verify against, so the benchmark
  accepts any `list[Chunk]` / `list[EvalCase]` instead of guessing at that
  module's API — plug in real demo chunks or a small hand-built corpus.
  Swapping in the real demo dataset, or the live ONNX embedder via
  `embedding_function=`, is a follow-up, not a blocker.

## How to run

```bash
python -m pytest tests/test_retrieval_grounding.py tests/test_retrieval_perf.py -v
python -m ruff check src/retrieval/verifier.py src/retrieval/evaluation.py \
    src/retrieval/performance.py src/retrieval/benchmark.py \
    tests/test_retrieval_grounding.py tests/test_retrieval_perf.py
python -m mypy src/retrieval --ignore-missing-imports
```

## Still open (not in this addendum)

- Wiring `GroundingVerificationRule` into `DEFAULT_RULES` / the real
  validation pipeline (needs a decision from Nour on how per-query context
  gets threaded through the review flow).
- Plugging `run_benchmark()` into the actual demo dataset once its shape is
  confirmed.
- Persisting benchmark results over time (currently one-shot, in-memory
  report only).
