"""Stage-by-stage timing for ingest, indexing and retrieval.

Run this before and after any change to chunking, embedding or the retrieval
config, and put both tables in the pull request. Every performance number in
``docs/retrieval-latency.md`` came from here.

The point is a comparable number, not a dashboard: one document, one query, one
table. It exists because "it feels slow" and "it got slower" are unarguable
until someone measures them.

Usage::

    python scripts/bench_ingest.py path/to/document.pdf
    python scripts/bench_ingest.py path/to/document.pdf --focus "thermal conduction"

Indexing is the expensive stage - roughly 97% of the total on a large document -
so expect a large file to take minutes on the first run.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.chunker import TextChunker  # noqa: E402
from src.ingestion.cleaner import TextCleaner  # noqa: E402
from src.ingestion.parser import TextParser  # noqa: E402
from src.ingestion.quality import QualityChecker  # noqa: E402
from src.retrieval import ChunkIndex  # noqa: E402
from src.study.grounding import grounded_content, index_chunks  # noqa: E402


def _stage(label: str, timings: dict[str, float]):
    """Time a block and record it in milliseconds."""

    class _Ctx:
        def __enter__(self) -> None:
            self._t0 = time.perf_counter()

        def __exit__(self, *_exc: object) -> None:
            timings[label] = (time.perf_counter() - self._t0) * 1000

    return _Ctx()


def main() -> int:
    """Measure one document end to end and print the stage table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", help="Path to a PDF, DOCX, MD or TXT file")
    parser.add_argument(
        "--focus",
        default="key concepts",
        help="Retrieval query, as the generation pages would supply",
    )
    args = parser.parse_args()

    path = Path(args.document)
    if not path.is_file():
        print(f"No such file: {path}", file=sys.stderr)
        return 1

    # Work in a scratch directory so a benchmark never writes to the repo's
    # database or a persisted index.
    os.chdir(tempfile.mkdtemp())

    data = path.read_bytes()
    suffix = path.suffix.lstrip(".").lower() or "txt"
    timings: dict[str, float] = {}

    with _stage("parse_ms", timings):
        raw = TextParser.parse(data, suffix)
    with _stage("clean_ms", timings):
        cleaned = TextCleaner.clean(raw)
    with _stage("quality_ms", timings):
        quality = QualityChecker().validate(cleaned)
    with _stage("chunk_ms", timings):
        chunker = TextChunker()
        chunks = chunker.chunk(cleaned, "bench")

    index = ChunkIndex()
    with _stage("embed_ms", timings):
        index_chunks(index, "bench", chunks)
    with _stage("retrieve_ms", timings):
        content, cited, _context = grounded_content(
            index=index, document_id="bench", focus=args.focus, topics=[]
        )

    print(f"file           {path.name}  ({len(data) / 1e6:.1f} MB)")
    print(f"chunk_size     {chunker.chunk_size}  overlap {chunker.overlap}")
    print(f"quality        passed={quality.passed}")
    print(f"n_chunks       {len(chunks):,}")
    print(f"n_retrieved    {len(cited)}  ({len(content):,} chars of prompt)")
    print()
    for label in (
        "parse_ms",
        "clean_ms",
        "quality_ms",
        "chunk_ms",
        "embed_ms",
        "retrieve_ms",
    ):
        print(f"  {label:<14}{timings[label]:>12,.1f} ms")
    print(f"  {'total':<14}{sum(timings.values()) / 1000:>12,.1f} s")

    slowest = max(timings, key=lambda key: timings[key])
    share = timings[slowest] / sum(timings.values()) * 100
    print()
    print(f"slowest stage: {slowest} at {share:.0f}% of the total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
