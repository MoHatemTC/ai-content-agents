"""Offline tests for the demo benchmark runner and report formatting."""

import json

from src.evaluation.demo_benchmark import (
    format_benchmark_summary,
    load_demo_inputs,
    run_demo_benchmark,
    save_benchmark_reports,
)
from tests.conftest import CompliantAgentsClient


def test_demo_benchmark_runs_both_agents_and_formats_reports(tmp_path):
    """The packaged dataset produces printable Mentor and Concept reports."""
    reports = run_demo_benchmark(load_demo_inputs(), client=CompliantAgentsClient())

    assert set(reports) == {"mentor", "concept"}
    for agent_name, report in reports.items():
        assert report.summary.total_processed == 2
        assert report.summary.total_succeeded == 2
        assert report.summary.total_failed == 0
        assert report.summary.average_groundedness_score == 1.0
        summary = format_benchmark_summary(agent_name, report)
        assert f"{agent_name.title()} benchmark" in summary
        assert "average groundedness: 1.00" in summary


def test_save_benchmark_reports_writes_json(tmp_path):
    """Optional report output is serialized as JSON for later inspection."""
    reports = run_demo_benchmark(load_demo_inputs(), client=CompliantAgentsClient())
    output_path = tmp_path / "benchmark-report.json"

    save_benchmark_reports(reports, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload) == {"mentor", "concept"}
    assert payload["mentor"]["summary"]["total_succeeded"] == 2
