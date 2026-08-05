# Chunking Strategy

## Overview

The ingestion pipeline uses a hierarchical chunking strategy designed to
preserve natural language structure while producing deterministic chunks for
retrieval.

The chunking process follows four levels:

1. Paragraphs
2. Sentences
3. Words
4. Characters (fallback)

The algorithm always attempts to split using the highest-level structure
available before falling back to a finer-grained split.

---

## Sentence Packing

Sentences are detected using punctuation (`.`, `!`, `?`) and packed together
until adding another sentence would exceed the configured `chunk_size`.

Example:

Chunk 1

Sentence one.
Sentence two.

Chunk 2

Sentence three.

---

## Overlap

Neighbouring chunks overlap by `chunk_overlap` characters, and the overlap
begins at a word boundary so no token is split.

**The overlap counts towards `chunk_size`.** Packing therefore fills only
`chunk_size - chunk_overlap` characters of new content, leaving room for the
carry-over, so a finished chunk is exactly at the ceiling rather than over it.

The two constraints pull against each other: packing to the full `chunk_size`
and then prepending the overlap breaches the ceiling, while clamping afterwards
satisfies the ceiling by leaving no room for overlap at all. Reserving it up
front is what satisfies both — and it matches the original character chunker,
whose stride was also `chunk_size - overlap`.

---

## Abbreviations and decimals

A period followed by a space does not always end a sentence, and study material
is full of the exceptions. A boundary is rejected when either holds:

- the token before the period is a known abbreviation — `Fig.`, `Eq.`, `Ch.`,
  `Sec.`, `Dr.`, `e.g.`, `i.e.`, and so on;
- running text continues after it — the next character is lowercase or a digit.

Both rules are needed. `Dr. Young` is followed by a capital, so only the list
catches it; `Tbl. 4` is in no list, so only the general rule does. The list can
never be complete, which is why the general rule sits behind it.

Decimals are safe without special handling: in `0.375` the period is followed by
a digit, not whitespace, so it is never a candidate boundary.

**Single letters are deliberately not treated as initials.** It is tempting —
`J. R. R. Tolkien` — but study material ends sentences on variables far more
often than it names people by initial: `where R = L / k.` and `T = 2.27 C.` both
close on a lone letter. Splitting a name into fragments costs nothing, because
packing reassembles them; merging two real sentences coarsens every chunk
boundary that follows.

---

## Long Sentences

If a single sentence exceeds `chunk_size`, it is split on word boundaries.

If a single word exceeds `chunk_size`, the algorithm falls back to character
splitting to guarantee progress.

---

## Determinism

Chunk generation is deterministic.

The same document always produces:

- identical chunk ids
- identical chunk boundaries
- identical chunk ordering

---

## Chunk IDs

Chunks use the format

```
{document_id}-c0000
{document_id}-c0001
...
```

The ids are stable for a given document and chunking configuration.

---

## Offset Tracking

Every chunk stores

- `start_char`
- `end_char`

These offsets always satisfy

```python
text[start_char:end_char] == chunk.text
```

allowing exact reconstruction of the original source.

---

## Changing the chunking changes every chunk id

Chunk ids are `{document_id}-c{ordinal:04d}`, so they are positional. Any change
to chunk boundaries renumbers them, and a citation stored against `doc-c0007`
before the change no longer points at the text it was recorded for.

**Documents must be re-ingested after a chunking change.** There is no migration
for this, and no way to detect it after the fact — a stale citation looks exactly
like a valid one.

---

## Measured effect

Sixty pages of a physics textbook (259,114 characters) at the defaults,
`chunk_size=1000, overlap=100`:

| | chunks | largest | over the limit | mid-word cuts |
|---|---|---|---|---|
| Character slicing (original) | — | 1000 | 0 | **every boundary** |
| Sentence packing, first cut | 282 | 1103 | **190** | 0 |
| Current | 326 | 1000 | **0** | 0 |

`See Fig. 21.5` survives intact in the current version and was severed in the
previous one.

### The retrieval benchmark cannot measure this

`src/retrieval/benchmark.py` reports recall@k `1.0` and MRR `1.0` both before and
after — byte-identical, down to a mean grounding confidence of
`0.44790985186894733`. That is not evidence of no effect: the demo corpus is
**five documents that produce five chunks**, one each, so chunking never runs at
a boundary and the benchmark is at its ceiling regardless.

Evaluating chunking strategy needs a corpus with multi-chunk documents and cases
whose answers straddle a boundary. Until that exists, changes here should be
justified by the table above rather than by the benchmark.

---

## Testing

`tests/features/test_chunking.py`, covering:

- sentence splitting, sentence packing, long-sentence and long-word handling
- word-boundary preservation
- `chunk_size` as a hard ceiling, across several size/overlap combinations
- overlap surviving that ceiling being enforced
- abbreviations and decimals staying intact, including ones absent from the list
- paragraphs packed whole rather than torn at sentence boundaries
- `text[start_char:end_char]` reproducing every chunk
- ingestion and retrieval producing identical chunks
- determinism, contiguous ordinals, empty input

Each test was mutation-verified: the defect it guards was reintroduced and the
test confirmed to fail, then restored. Worth keeping up — two tests written for
this file passed their mutation on the first attempt and had to be rewritten,
which is the failure mode a green suite hides.