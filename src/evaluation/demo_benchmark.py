"""CLI for running the offline Mentor and Concept demo benchmark."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.evaluation import BenchmarkInput, BenchmarkReport, run_benchmark

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "demo_benchmark.json"
)


def load_demo_inputs(dataset_path: Path = DEFAULT_DATASET_PATH) -> list[BenchmarkInput]:
    """Load and validate benchmark inputs from a JSON dataset."""
    with dataset_path.open("r", encoding="utf-8") as dataset_file:
        raw_items = json.load(dataset_file)
    if not isinstance(raw_items, list):
        raise ValueError("The demo benchmark dataset must contain a JSON list.")
    return [BenchmarkInput.model_validate(item) for item in raw_items]


def run_demo_benchmark(
    inputs: list[BenchmarkInput],
    *,
    client: Any | None = None,
) -> dict[str, BenchmarkReport]:
    """Run the loaded inputs through both agents.

    Args:
        inputs: Benchmark rows.
        client: An OpenAI-compatible client shared by both agents. Defaults to
            one built from the configured gateway; tests inject a double. This
            used to run in mock mode, which meant it benchmarked the mock.
    """
    return {
        "mentor": run_benchmark(MentorAgent(client=client), inputs),
        "concept": run_benchmark(ConceptAgent(client=client), inputs),
    }


def format_benchmark_summary(
    agent_name: str,
    report: BenchmarkReport,
) -> str:
    """Format one benchmark report as a concise human-readable summary."""
    summary = report.summary
    groundedness = (
        "not evaluated"
        if summary.average_groundedness_score is None
        else f"{summary.average_groundedness_score:.2f}"
    )
    groundedness_ratio = (
        "not evaluated"
        if summary.average_groundedness_ratio is None
        else f"{summary.average_groundedness_ratio:.2f}"
    )
    difficulty_alignment = (
        "not evaluated"
        if summary.average_difficulty_alignment_score is None
        else f"{summary.average_difficulty_alignment_score:.2f}"
    )
    return "\n".join(
        [
            f"{agent_name.title()} benchmark",
            f"  processed: {summary.total_processed}",
            f"  succeeded: {summary.total_succeeded}",
            f"  failed: {summary.total_failed}",
            f"  average groundedness: {groundedness}",
            f"  average groundedness ratio: {groundedness_ratio}",
            f"  average difficulty alignment: {difficulty_alignment}",
            f"  average quality: {summary.average_quality_score:.2f}",
            f"  reference validity: {summary.reference_validity_rate:.2f}",
            f"  support rate: {summary.support_rate:.2f}",
            f"  validation pass rate: {summary.validation_pass_rate:.2f}",
            f"  elapsed seconds: {summary.elapsed_seconds:.3f}",
        ]
    )


def save_benchmark_reports(
    reports: dict[str, BenchmarkReport],
    output_path: Path,
) -> None:
    """Save combined benchmark reports as readable JSON."""
    payload = {
        agent_name: report.model_dump(mode="json")
        for agent_name, report in reports.items()
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the demo benchmark CLI and optionally save its reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to a JSON list of benchmark inputs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for the combined JSON benchmark report.",
    )
    args = parser.parse_args(argv)

    reports = run_demo_benchmark(load_demo_inputs(args.dataset))
    print(
        "\n\n".join(
            format_benchmark_summary(agent_name, report)
            for agent_name, report in reports.items()
        )
    )
    if args.output_json is not None:
        save_benchmark_reports(reports, args.output_json)
        print(f"\nSaved benchmark report to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
