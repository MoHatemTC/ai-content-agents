"""Batch automation: run the whole pipeline over a demo dataset, unattended.

Turns the demo from "click through the UI a few times" into one reproducible
command. For each document in the dataset it ingests the material, grounds the
question, runs the selected agents, validates and persists everything, then
scores the result with :mod:`src.validation.evaluation`.

The batch is built to survive a bad day. One document failing, one agent
failing, or the whole gateway being down produces recorded failures and a report
that says so — never a half-finished run that raises on the way out. That
matters because the interesting failures (a dead upstream, a model returning
prose instead of JSON) are exactly the ones a batch is likely to hit.

Nothing here exports anything. Every output lands in ``pending`` and waits for a
human, which is the entire point of the review gate.

Run it with::

    python -m src.validation.automation              # every agent
    python -m src.validation.automation --limit 1    # one document
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.retrieval.config import RetrievalConfig
from src.retrieval.index import ChunkIndex
from src.validation.evaluation import EvaluationHarness, EvaluationReport
from src.validation.history import BATCH_COMPLETED, BATCH_STARTED
from src.validation.integration import Pipeline
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoDocument:
    """One item of the demo dataset: material plus a question to ask about it.

    Attributes:
        title: Document title, also used as the ingestion title.
        text: The study material to ingest.
        query: The learner question to ground and answer.
    """

    title: str
    text: str
    query: str


# Kept inline rather than in a data file so the batch runs from a fresh clone
# with nothing to download, and so it cannot collide with another lane's demo
# fixtures. Pass --dataset to use your own material instead.
DEMO_DATASET: tuple[DemoDocument, ...] = (
    DemoDocument(
        title="Newtonian mechanics",
        text=(
            "Newton's first law states that an object stays at rest or moves at "
            "constant velocity unless a net external force acts on it.\n\n"
            "Newton's second law states that force equals mass times "
            "acceleration, so a larger force produces a larger acceleration for "
            "the same mass.\n\n"
            "Newton's third law states that for every action there is an equal "
            "and opposite reaction."
        ),
        query="what does newton's second law say about force and acceleration",
    ),
    DemoDocument(
        title="Python control flow",
        text=(
            "A for loop repeats a block of code once for each item in a "
            "sequence, such as a list or a string.\n\n"
            "A while loop repeats a block of code for as long as its condition "
            "stays true, so the condition must eventually become false to avoid "
            "an infinite loop.\n\n"
            "The break statement exits a loop immediately, while continue skips "
            "to the next iteration."
        ),
        query="what is the difference between a for loop and a while loop",
    ),
    DemoDocument(
        title="Cell biology basics",
        text=(
            "The cell membrane controls which substances enter and leave the "
            "cell, forming a selective barrier around it.\n\n"
            "Mitochondria release energy from glucose through respiration, "
            "which is why they are described as the powerhouse of the cell.\n\n"
            "The nucleus stores the cell's genetic material and directs its "
            "activities."
        ),
        query="what do mitochondria do in a cell",
    ),
)


@dataclass
class BatchItemResult:
    """The outcome of processing one document.

    Attributes:
        title: The document's title.
        document_id: The ingested document's id, when ingestion succeeded.
        run_ids: Ids of the agent runs it produced.
        output_ids: Ids of the outputs it produced.
        validated: Outputs that passed validation.
        error: Why this item produced nothing, when it did not.
    """

    title: str
    document_id: str | None = None
    run_ids: list[str] = field(default_factory=list)
    output_ids: list[str] = field(default_factory=list)
    validated: int = 0
    error: str | None = None


@dataclass
class BatchReport:
    """The outcome of a whole batch, plus its evaluation.

    Attributes:
        items: Per-document outcomes, in dataset order.
        elapsed_seconds: Wall-clock duration of the batch.
        evaluation: Metrics scored over the runs this batch produced.
    """

    items: list[BatchItemResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    evaluation: EvaluationReport | None = None

    @property
    def run_ids(self) -> list[str]:
        """Every agent run id produced by the batch."""
        return [run_id for item in self.items for run_id in item.run_ids]

    @property
    def output_ids(self) -> list[str]:
        """Every output id produced by the batch."""
        return [output_id for item in self.items for output_id in item.output_ids]

    @property
    def failed_items(self) -> list[BatchItemResult]:
        """Documents that produced nothing at all."""
        return [item for item in self.items if item.error is not None]

    def render(self) -> str:
        """Render the batch and its metrics as a plain-text report.

        Returns:
            A human-readable summary suitable for a terminal or a PR comment.
        """
        lines = [
            "Batch run",
            "=" * 60,
            f"documents : {len(self.items)}",
            f"runs      : {len(self.run_ids)}",
            f"outputs   : {len(self.output_ids)} (all pending human review)",
            f"elapsed   : {self.elapsed_seconds:.1f}s",
            "",
        ]

        for item in self.items:
            status = (
                f"FAILED - {item.error}"
                if item.error
                else (
                    f"{len(item.output_ids)} output(s), {item.validated} passed validation"
                )
            )
            lines.append(f"  {item.title}: {status}")

        if self.evaluation is not None:
            lines += ["", "Evaluation", "-" * 60]
            rows = self.evaluation.summary_rows()
            if rows:
                headers = list(rows[0])
                widths = [
                    max(len(str(header)), *(len(str(row[header])) for row in rows))
                    for header in headers
                ]
                lines.append(
                    "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
                )
                for row in rows:
                    lines.append(
                        "  ".join(str(row[h]).ljust(w) for h, w in zip(headers, widths))
                    )

        return "\n".join(lines)


def load_dataset(path: str | Path) -> list[DemoDocument]:
    """Load a demo dataset from a JSON file.

    Args:
        path: A JSON file holding a list of ``{title, text, query}`` objects.

    Returns:
        The parsed dataset.

    Raises:
        ValueError: If the file is not a list of objects with the right keys.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of documents.")
    try:
        return [
            DemoDocument(title=item["title"], text=item["text"], query=item["query"])
            for item in data
        ]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"{path}: every entry needs 'title', 'text' and 'query' keys."
        ) from exc


def run_batch(
    dataset: Sequence[DemoDocument] | None = None,
    *,
    pipeline: Pipeline | None = None,
    agents: Sequence[str] | None = None,
    limit: int | None = None,
    db_path: str = "ingestion.db",
    client: Any | None = None,
    evaluate: bool = True,
) -> BatchReport:
    """Run the pipeline over a dataset and score the result.

    Args:
        dataset: Documents to process; defaults to :data:`DEMO_DATASET`.
        pipeline: An assembled pipeline; one is built if omitted.
        agents: Which agents to run per document; defaults to all registered.
        limit: Process at most this many documents.
        db_path: Database file for the ingestion and platform stores.
        client: An OpenAI-compatible client shared by every agent; tests
            inject a double.
        evaluate: Whether to score the batch afterwards.

    Returns:
        The :class:`BatchReport`. Individual failures are recorded in it rather
        than raised, so a batch always returns something to look at.
    """
    documents = list(dataset if dataset is not None else DEMO_DATASET)
    if limit is not None:
        documents = documents[:limit]

    pipe = pipeline or Pipeline.build(
        db_path=db_path,
        # A unique collection keeps repeat batches from stacking up in Chroma's
        # process-wide ephemeral client.
        index=ChunkIndex(RetrievalConfig(collection_name=f"batch-{uuid4().hex}")),
        client=client,
    )
    store: PlatformStore = pipe.platform_store

    store.log_event(
        BATCH_STARTED,
        f"Batch started over {len(documents)} document(s)",
        details={"documents": [document.title for document in documents]},
    )
    started = time.monotonic()
    report = BatchReport()

    for document in documents:
        report.items.append(_run_one(pipe, document, agents))

    report.elapsed_seconds = time.monotonic() - started

    if evaluate:
        report.evaluation = EvaluationHarness(store).evaluate(run_ids=report.run_ids)

    store.log_event(
        BATCH_COMPLETED,
        f"Batch produced {len(report.output_ids)} output(s) "
        f"from {len(report.run_ids)} run(s)",
        details={
            "documents": len(report.items),
            "failed_documents": len(report.failed_items),
            "elapsed_seconds": round(report.elapsed_seconds, 2),
        },
    )
    return report


def _run_one(
    pipeline: Pipeline, document: DemoDocument, agents: Sequence[str] | None
) -> BatchItemResult:
    """Process one document, converting any failure into a recorded result."""
    item = BatchItemResult(title=document.title)
    try:
        result = pipeline.ingest_and_run(
            document.text,
            document.query,
            title=document.title,
            agents=agents,
        )
    except Exception as exc:
        item.error = f"{type(exc).__name__}: {exc}"
        logger.exception("batch item %r failed", document.title)
        return item

    if result.error is not None:
        item.error = result.error
        return item

    item.run_ids = [run_result.run.id for run_result in result.results]
    item.output_ids = [output.id for output in result.outputs]
    item.validated = sum(1 for output in result.outputs if output.validation_passed)
    return item


def main(argv: Sequence[str] | None = None) -> int:
    """Run a batch from the command line and print the report.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` when every document produced at least one output, ``1`` otherwise,
        so the command is usable as a check.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.validation.automation",
        description=(
            "Run the ingest -> retrieve -> agents -> validate pipeline over a "
            "demo dataset and print the evaluation report. Outputs are left "
            "pending human review; nothing is exported."
        ),
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        metavar="NAME",
        help="Agents to run per document (default: every registered agent).",
    )
    parser.add_argument(
        "--limit", type=int, metavar="N", help="Process at most N documents."
    )
    parser.add_argument(
        "--dataset", metavar="PATH", help="JSON dataset to use instead of the built-in."
    )
    parser.add_argument(
        "--db", default="ingestion.db", metavar="PATH", help="SQLite database path."
    )
    parser.add_argument(
        "--no-evaluation", action="store_true", help="Skip the evaluation report."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    dataset = load_dataset(args.dataset) if args.dataset else None
    report = run_batch(
        dataset,
        agents=args.agents,
        limit=args.limit,
        db_path=args.db,
        evaluate=not args.no_evaluation,
    )

    print(report.render())

    if report.failed_items:
        print(f"\n{len(report.failed_items)} document(s) produced no output.")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
