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

Neighbouring chunks overlap by `chunk_overlap` characters.

Whenever possible the overlap begins at a word boundary to avoid splitting
tokens.

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

## Testing

The chunker is verified with tests covering:

- sentence splitting
- sentence packing
- overlap preservation
- word-boundary preservation
- long-word handling
- long-sentence handling
- deterministic output