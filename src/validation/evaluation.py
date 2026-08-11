"""AI evaluation harness: measure what the platform actually produced.

Reads the persisted record — runs, outputs, verdicts and reviews — and reports
three rates the brief asks for, overall and per agent:

* **schema pass rate** — how often an agent returned something that satisfied
  its declared schema *and* the guardrails;
* **groundedness rate** — how often its citations pointed at chunks that were
  genuinely retrieved, from the ``grounding_verification`` guardrail's verdict;
* **review edit rate** — how often a human had to change the output before
  approving it, the most honest quality signal available because it is a
  person's judgement rather than a heuristic.

Approval and rejection rates come along for free and answer the question
reviewers actually ask: how much of this was usable?

The harness makes **no model calls**. It is a pure read over the database, so
the same batch can be re-scored repeatedly and the numbers are reproducible.
That also means it measures whatever is in the store: score a batch run against
a dead gateway and you will correctly see zero outputs, not a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field

from src.validation.review_schema import (
    GeneratedOutput,
    OutputStatus,
    ReviewAction,
    RunStatus,
)
from src.validation.store import PlatformStore

logger = logging.getLogger(__name__)

GROUNDING_RULE = "grounding_verification"


def _rate(numerator: int, denominator: int) -> float | None:
    """Return a ratio, or ``None`` when there is nothing to divide by.

    ``None`` rather than ``0.0`` on purpose: "no output was ever grounded" and
    "no output was ever checked for grounding" are different facts, and
    reporting the second as a zero would be misleading.
    """
    if denominator == 0:
        return None
    return numerator / denominator


class AgentMetrics(BaseModel):
    """Quality metrics for one agent (or for everything, when aggregated).

    Attributes:
        agent_name: The agent these metrics describe, or ``"overall"``.
        runs: Agent invocations recorded.
        failed_runs: Invocations that never produced an output.
        outputs: Outputs produced.
        schema_valid: Outputs whose schema check passed.
        validation_passed: Outputs that passed schema *and* guardrails.
        grounding_checked: Outputs where citations could be verified.
        grounded: Outputs whose citations were all genuinely retrieved.
        reviewed: Outputs a human has acted on.
        edited: Outputs a human changed before deciding.
        approved: Outputs approved for export.
        rejected: Outputs turned down.
    """

    agent_name: str
    runs: int = 0
    failed_runs: int = 0
    outputs: int = 0
    schema_valid: int = 0
    validation_passed: int = 0
    grounding_checked: int = 0
    grounded: int = 0
    reviewed: int = 0
    edited: int = 0
    approved: int = 0
    rejected: int = 0

    @property
    def run_success_rate(self) -> float | None:
        """Share of invocations that produced an output at all."""
        return _rate(self.runs - self.failed_runs, self.runs)

    @property
    def schema_pass_rate(self) -> float | None:
        """Share of outputs that satisfied their schema and guardrails."""
        return _rate(self.validation_passed, self.outputs)

    @property
    def schema_only_pass_rate(self) -> float | None:
        """Share of outputs that parsed against their schema, guardrails aside."""
        return _rate(self.schema_valid, self.outputs)

    @property
    def groundedness_rate(self) -> float | None:
        """Share of *checkable* outputs whose citations were all real."""
        return _rate(self.grounded, self.grounding_checked)

    @property
    def review_edit_rate(self) -> float | None:
        """Share of reviewed outputs a human had to change."""
        return _rate(self.edited, self.reviewed)

    @property
    def approval_rate(self) -> float | None:
        """Share of reviewed outputs that were approved."""
        return _rate(self.approved, self.reviewed)

    @property
    def rejection_rate(self) -> float | None:
        """Share of reviewed outputs that were turned down."""
        return _rate(self.rejected, self.reviewed)


class EvaluationReport(BaseModel):
    """The result of scoring a slice of the platform's history."""

    overall: AgentMetrics
    per_agent: dict[str, AgentMetrics] = Field(default_factory=dict)

    def summary_rows(self) -> list[dict[str, object]]:
        """Render the report as rows for a table or a CLI dump.

        Returns:
            One row per agent plus an ``overall`` row last, with rates rendered
            as percentages and ``None`` shown as ``"n/a"``.
        """

        def render(metrics: AgentMetrics) -> dict[str, object]:
            return {
                "agent": metrics.agent_name,
                "runs": metrics.runs,
                "failed runs": metrics.failed_runs,
                "outputs": metrics.outputs,
                "schema pass": _percent(metrics.schema_pass_rate),
                "grounded": _percent(metrics.groundedness_rate),
                "reviewed": metrics.reviewed,
                "review edit": _percent(metrics.review_edit_rate),
                "approved": _percent(metrics.approval_rate),
            }

        return [render(m) for m in self.per_agent.values()] + [render(self.overall)]


def _percent(value: float | None) -> str:
    """Render a rate as a percentage, or ``"n/a"`` when it is undefined."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


class EvaluationHarness:
    """Scores generated outputs from the persisted record.

    Args:
        store: The store to read runs, outputs and reviews from.
    """

    def __init__(self, store: PlatformStore) -> None:
        self._store = store

    def evaluate(
        self,
        *,
        agent_name: str | None = None,
        run_ids: Sequence[str] | None = None,
    ) -> EvaluationReport:
        """Score a slice of the platform's history.

        Args:
            agent_name: Restrict to one agent.
            run_ids: Restrict to specific runs, e.g. the runs of one batch.

        Returns:
            The report, with per-agent metrics and an aggregate.
        """
        runs = self._store.list_agent_runs(agent_name=agent_name)
        if run_ids is not None:
            wanted = set(run_ids)
            runs = [run for run in runs if run.id in wanted]

        per_agent: dict[str, AgentMetrics] = {}
        for run in runs:
            metrics = per_agent.setdefault(
                run.agent_name, AgentMetrics(agent_name=run.agent_name)
            )
            metrics.runs += 1
            if run.status is RunStatus.FAILURE:
                metrics.failed_runs += 1

            for output in self._store.list_outputs(agent_run_id=run.id):
                self._score_output(metrics, output)

        overall = self._aggregate(per_agent.values())
        logger.info("evaluated %d run(s) across %d agent(s)", len(runs), len(per_agent))
        return EvaluationReport(
            overall=overall, per_agent=dict(sorted(per_agent.items()))
        )

    def _score_output(self, metrics: AgentMetrics, output: GeneratedOutput) -> None:
        """Fold one output's verdict and review history into an agent's metrics."""
        metrics.outputs += 1

        report = output.validation_report or {}
        if not report.get("schema_errors"):
            metrics.schema_valid += 1
        if output.validation_passed:
            metrics.validation_passed += 1

        violations = report.get("guardrail_violations") or []
        if self._grounding_was_checked(output, report):
            metrics.grounding_checked += 1
            if not any(v.get("rule_name") == GROUNDING_RULE for v in violations):
                metrics.grounded += 1

        reviews = self._store.list_reviews(output_id=output.id)
        decisions = [r for r in reviews if r.action is not ReviewAction.COMMENT]
        if decisions:
            metrics.reviewed += 1
            if any(r.action is ReviewAction.EDIT for r in decisions):
                metrics.edited += 1

        if output.status is OutputStatus.APPROVED:
            metrics.approved += 1
        elif output.status is OutputStatus.REJECTED:
            metrics.rejected += 1

    def _grounding_was_checked(
        self, output: GeneratedOutput, report: dict[str, object]
    ) -> bool:
        """Return whether this output's citations could be verified at all.

        The grounding rule is a no-op for ungrounded runs, so counting those as
        "not grounded" would understate quality. An output counts as checkable
        when its schema check passed (guardrails ran) and the generating run
        recorded the chunk ids to check against.
        """
        if report.get("schema_errors"):
            return False  # Guardrails never ran.
        run = self._store.get_agent_run(output.agent_run_id)
        return bool(run and run.source_chunk_ids)

    @staticmethod
    def _aggregate(all_metrics: object) -> AgentMetrics:
        """Sum per-agent metrics into a single overall record."""
        overall = AgentMetrics(agent_name="overall")
        for metrics in all_metrics:  # type: ignore[attr-defined]
            for field_name in AgentMetrics.model_fields:
                if field_name == "agent_name":
                    continue
                setattr(
                    overall,
                    field_name,
                    getattr(overall, field_name) + getattr(metrics, field_name),
                )
        return overall
