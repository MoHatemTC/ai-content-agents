# Retrieval & Grounding Lane

Scoped top-k retrieval with provenance over ingested content, and the
grounded-context payload agents consume so answers stay grounded in uploaded
material. Self-contained under `src/retrieval/`; integrates with the rest of
the project only through shared contracts (`ContentReference`,
`AgentRun.source_chunk_ids`, the prompt `{content}` placeholder).

## retrieval_design

**Choice: Chroma as a local embedded vector store** (`chromadb`, added to
`requirements.txt`; verified working: 1.5.9 on Python 3.14/Windows).

Why Chroma:

- **Semantic matching** — paraphrased questions still find relevant chunks,
  the known weakness of purely lexical scoring.
- **Scope enforcement inside the store** — metadata `where` filters apply
  *before* the similarity search, so out-of-scope chunks are never even
  candidates (see `topk_retrieval`).
- **Incremental by construction** — `upsert`/`delete` update the index in
  place; no rebuild step exists anywhere in this lane.
- **Persistence for free** — `RetrievalConfig.persist_directory` switches the
  same code from in-memory (`EphemeralClient`) to on-disk
  (`PersistentClient`).

Embedder selection follows the repo's `MOCK_MODE` convention (offline by
default, like the agents' mock mode):

| `MOCK_MODE` | Embedder | Network |
|---|---|---|
| `true` (default) | `HashingEmbeddingFunction` — deterministic CRC32 bag-of-words, L2-normalized | none, ever |
| `false` | Chroma's default ONNX MiniLM model | one-time ~80 MB model download |

An explicit `embedding_function=` argument to `ChunkIndex` overrides both.
The whole test suite injects the hashing embedder and runs offline.

Rejected alternatives:

| Option | Why not |
|---|---|
| stdlib BM25 / rank-bm25 / sklearn TF-IDF | lexical only (no paraphrase); rank-bm25 rebuilds its corpus on every add; sklearn is a heavy dep for TF-IDF alone |
| Qdrant | requires a running server — too much infrastructure for this stage |
| LiteLLM `/embeddings` | the Sprints proxy's embeddings route is unverified; would also make retrieval network-dependent |

Swap path: `Retriever` is a `typing.Protocol` with a single `retrieve`
method — an alternative backend implements it and nothing else changes
(`build_grounded_context`, payload, consumers, tests all survive).

## grounding_contract

**Given a query and a selected document/session, return grounded context
chunks with provenance:**

```python
from src.retrieval import (
    ChunkIndex, ChromaRetriever, RetrievalScope, build_grounded_context,
)

retriever = ChromaRetriever(index)
context = build_grounded_context(
    "What is Newton's second law?",
    RetrievalScope(session_id="session-1"),   # and/or document_id=...
    retriever,
)
```

`RetrievalScope` **requires** at least one of `document_id` / `session_id`
(an unscoped retrieval is a `ValidationError`), so when grounding is
required, content outside the selection can never be returned — the
guarantee is structural, not a convention.

The returned `GroundedContext` is consumed three ways:

| Consumer | API | Feeds |
|---|---|---|
| Agent prompt | `context.as_prompt_content()` | the `{content}` placeholder in `src/prompts/*.yaml` (chunks rendered as `[chunk_id]` + text so the model cites stable ids) |
| Agent output | `context.to_content_references()` | `MentorOutput.references` / `ConceptOutput.references` (`ContentReference` objects — satisfies the `ReferencesPresentRule` guardrail) |
| Review/provenance | `context.chunk_ids` | `AgentRun.source_chunk_ids` (+ `as_prompt_content()` for `AgentRun.input_context`) |

When nothing relevant exists in scope, `context.is_sufficient` is `False`
and `as_prompt_content()` raises `InsufficientGroundingError` — an agent can
never be silently invoked ungrounded.

QA-side complement: `verify_references(references, context)` checks that
every cited `segment_id` was actually retrieved, flagging fabricated
citations (`GroundingVerification.unknown_segment_ids`). The validation lane
can adopt it as a guardrail later without this lane depending on validation
internals.

## index_scaffold

`ChunkIndex` (in `src/retrieval/index.py`) wraps one Chroma collection
(cosine space, telemetry disabled) and is the single source of truth — no
parallel in-memory state to drift. Each chunk is stored with its text plus
`document_id` / `session_id` / `ordinal` metadata, which is what scoped
retrieval filters on.

Ingestion produces `Chunk` records via `split_text_into_chunks(text,
document_id=..., session_id=...)`: paragraphs are greedily packed up to
`chunk_size` characters; a single oversized paragraph falls back to a
word-window split with `chunk_overlap` characters of overlap. Chunk ids are
deterministic and citation-safe: `f"{document_id}-c{ordinal:04d}"` with the
document id sanitized to `[A-Za-z0-9_-]`. (This helper stands in for the
not-yet-built ingestion lane; an ingestion service can also supply its own
`Chunk` records directly.)

## topk_retrieval

`ChromaRetriever.retrieve(query, scope, top_k=None)`:

1. `scope.to_where()` builds the metadata filter (single clause, or `$and`
   when both document and session are set) — Chroma applies it **before**
   the nearest-neighbour search, so out-of-scope chunks are never scored,
   ranked, or returned.
2. Cosine distances convert to similarity scores (`score = 1 - distance`).
3. Results at or below `min_score` are dropped (default `0.0`, so
   zero-similarity matches never surface; raise it to require stronger
   matches).
4. Deterministic ordering by `(-score, ordinal, chunk_id)`, truncation to
   `top_k` (default `RetrievalConfig.top_k = 5`), 1-based ranks.

Blank queries and empty scopes return `[]` — "nothing relevant" is a valid
retrieval outcome; deciding whether it is *sufficient* is the grounding
layer's job.

## grounded_context

Payload shape (`src/retrieval/models.py`):

```
GroundedContext
├── query: str
├── scope: RetrievalScope(document_id?, session_id?)
└── chunks: list[RetrievedChunk]
    ├── chunk: Chunk(chunk_id, document_id, session_id?, ordinal, text)
    ├── score: float      # cosine similarity
    └── rank: int         # 1-based
```

`as_prompt_content()` renders:

```
[physics-notes-c0000]
Newton's second law states that force equals mass times acceleration.

[physics-notes-c0001]
Acceleration measures how quickly velocity changes over time.
```

Chunk text is inserted into prompt templates verbatim — `str.format` does
not re-process substituted values, so braces in uploaded content (e.g. code
snippets) are safe without escaping (covered by a pipeline test).

## incremental_index

- `add_chunks(chunks)` **upserts**: new content extends the index in place;
  re-adding a chunk id overwrites rather than duplicates. Newly added
  content is immediately retrievable (covered by a pipeline test).
- `add_document(document_id, chunks)` has **replace semantics**: previous
  chunks of that document are deleted first, so re-ingesting an updated
  document never leaves stale chunks and never inflates rankings with
  duplicates.
- `remove_document(document_id)` purges a document entirely.
- There is no rebuild operation anywhere — the index only ever moves
  forward incrementally.

Note: Chroma's `EphemeralClient` shares one in-process instance, so two
in-memory `ChunkIndex` objects with the same `collection_name` see the same
data (database-like behavior). Use distinct collection names for isolation
(the tests do).

## tests

- `tests/test_retrieval.py` — 49 unit tests: config validation, chunk/scope
  models (including the unscoped-retrieval `ValidationError`), splitter
  (packing, overlap windows, id sanitization), embedder determinism, index
  (roundtrip, incremental add, replace-on-reingest, remove), retriever
  (relevance sanity, **document/session scope isolation — the "never leak"
  requirement**, intersection scopes, top-k, min_score, deterministic
  tie-breaks, blank/empty edges), and the grounding contract.
- `tests/test_retrieval_pipeline.py` — 7 end-to-end tests against the real
  shared contracts: scoped ingestion → retrieval → the actual
  `mentor.yaml` template render → `ReferencesPresentRule` → fabricated
  citation detection → `AgentRun` provenance wiring → insufficient
  grounding → incremental ingestion.

All tests run offline and deterministic (hashing embedder injected;
`MOCK_MODE=true` pinned by `tests/conftest.py`).

Run:

```bash
python -m pytest tests/test_retrieval.py tests/test_retrieval_pipeline.py -v
python -m ruff check src/retrieval tests/test_retrieval.py tests/test_retrieval_pipeline.py
python -m mypy src/retrieval --ignore-missing-imports
```
