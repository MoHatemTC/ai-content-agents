"""Quality + groundedness benchmark harness for the AI evaluation workstream.

The evaluation module takes a :class:`BatchReport` from
:mod:`src.study.batch` and computes deterministic, auditable quality
metrics across three axes:

1. **Schema validation** - the Pydantic models already enforce this at
   construction, but the evaluator double-checks the gate flags and the
   structural invariants (non-empty outputs, valid dates, etc.).
2. **Groundedness** - the core metric: every topic / source_topic cited by
   a generated output must be a member of the *deterministically extracted*
   topic allow-list computed via :meth:`FlashcardAgent.extract_topics`. Any
   output referencing an extracted-topic it was NOT allowed to reference
   counts as ``grounded=False``.
3. **Completeness** - for flashcards, did we produce the requested card
   count? For plans / revisions, are all requested topics scheduled?

The evaluator never trusts the LLM or performs any network call. It runs
purely locally against the batch report and the original dataset, so the
resulting numbers are reproducible in CI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.schemas import FlashcardSet
from src.study.batch import (
    BatchFlashcardResult,
    BatchPlanResult,
    BatchReport,
    BatchRevisionResult,
    DemoDatasetItem,
    default_demo_dataset,
)
from src.study.flashcard_agent import FlashcardAgent
from src.study.schemas import RevisionSession, StudyPlan


@dataclass
class FlashcardQuality:
    total_outputs: int = 0
    schema_valid: int = 0
    gate_flag_set: int = 0
    grounded: int = 0
    count_matches_request: int = 0
    format_matches_request: int = 0

    @property
    def grounded_rate(self) -> float:
        return self.grounded / self.total_outputs if self.total_outputs else 0.0

    @property
    def overall_quality(self) -> float:
        if not self.total_outputs:
            return 0.0
        scores = [
            self.schema_valid,
            self.gate_flag_set,
            self.grounded,
            self.count_matches_request,
            self.format_matches_request,
        ]
        return sum(scores) / (len(scores) * self.total_outputs)


@dataclass
class PlanQuality:
    total_outputs: int = 0
    schema_valid: int = 0
    gate_flag_set: int = 0
    grounded: int = 0
    all_extracted_topics_scheduled: int = 0
    dates_in_window: int = 0

    @property
    def grounded_rate(self) -> float:
        return self.grounded / self.total_outputs if self.total_outputs else 0.0

    @property
    def overall_quality(self) -> float:
        if not self.total_outputs:
            return 0.0
        scores = [
            self.schema_valid,
            self.gate_flag_set,
            self.grounded,
            self.all_extracted_topics_scheduled,
            self.dates_in_window,
        ]
        return sum(scores) / (len(scores) * self.total_outputs)


@dataclass
class RevisionQuality:
    total_outputs: int = 0
    schema_valid: int = 0
    gate_flag_set: int = 0
    grounded: int = 0
    covers_all_selected: int = 0
    spaced_repetition_offsets_valid: int = 0

    @property
    def grounded_rate(self) -> float:
        return self.grounded / self.total_outputs if self.total_outputs else 0.0

    @property
    def overall_quality(self) -> float:
        if not self.total_outputs:
            return 0.0
        scores = [
            self.schema_valid,
            self.gate_flag_set,
            self.grounded,
            self.covers_all_selected,
            self.spaced_repetition_offsets_valid,
        ]
        return sum(scores) / (len(scores) * self.total_outputs)


@dataclass
class BenchmarkReport:
    flashcards: FlashcardQuality
    plans: PlanQuality
    revisions: RevisionQuality

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        data["flashcards"] = asdict(self.flashcards)
        data["flashcards"]["grounded_rate"] = round(self.flashcards.grounded_rate, 3)
        data["flashcards"]["overall_quality"] = round(
            self.flashcards.overall_quality, 3
        )
        data["plans"] = asdict(self.plans)
        data["plans"]["grounded_rate"] = round(self.plans.grounded_rate, 3)
        data["plans"]["overall_quality"] = round(self.plans.overall_quality, 3)
        data["revisions"] = asdict(self.revisions)
        data["revisions"]["grounded_rate"] = round(self.revisions.grounded_rate, 3)
        data["revisions"]["overall_quality"] = round(self.revisions.overall_quality, 3)
        data["overall"] = round(
            (
                self.flashcards.overall_quality
                + self.plans.overall_quality
                + self.revisions.overall_quality
            )
            / 3,
            3,
        )
        return data


def _title_to_item(
    dataset: list[DemoDatasetItem],
) -> dict[str, DemoDatasetItem]:
    return {item.title: item for item in dataset}


def _evaluate_flashcards(
    results: list[BatchFlashcardResult],
    dataset: list[DemoDatasetItem],
    *,
    expected_format: str = "term-definition",
    expected_count: int = 5,
) -> FlashcardQuality:
    title_to_item = _title_to_item(dataset)
    q = FlashcardQuality(total_outputs=len(results))
    for r in results:
        item = title_to_item.get(r.title)
        if r.error:
            continue
        cs: FlashcardSet = r.card_set
        q.schema_valid += 1
        if cs.needs_human_review:
            q.gate_flag_set += 1
        if item is not None:
            allowed = set(FlashcardAgent.extract_topics(item.content))
            topics_in_cards = {
                card.source_topic for card in cs.cards if card.source_topic
            }
            if topics_in_cards.issubset(allowed):
                q.grounded += 1
        if len(cs.cards) == expected_count:
            q.count_matches_request += 1
        card_formats = {card.format for card in cs.cards}
        if len(card_formats) == 1 and expected_format in card_formats:
            q.format_matches_request += 1
    return q


def _evaluate_plans(
    results: list[BatchPlanResult],
    dataset: list[DemoDatasetItem],
) -> PlanQuality:
    title_to_item = _title_to_item(dataset)
    q = PlanQuality(total_outputs=len(results))
    for r in results:
        if r.error or r.plan is None:
            continue
        plan: StudyPlan = r.plan
        q.schema_valid += 1
        if plan.needs_human_review:
            q.gate_flag_set += 1
        item = title_to_item.get(r.title)
        if item is not None:
            allowed = set(FlashcardAgent.extract_topics(item.content))
            scheduled = {s.topic for s in plan.topic_schedule}
            if scheduled.issubset(allowed):
                q.grounded += 1
            if allowed.issubset(scheduled):
                q.all_extracted_topics_scheduled += 1
        # Dates in window
        all_in_window = True
        for s in plan.topic_schedule:
            if s.start_date < plan.start_date or s.end_date > plan.end_date:
                all_in_window = False
                break
        if all_in_window:
            q.dates_in_window += 1
    return q


def _evaluate_revisions(
    results: list[BatchRevisionResult],
    dataset: list[DemoDatasetItem],
) -> RevisionQuality:
    title_to_item = _title_to_item(dataset)
    q = RevisionQuality(total_outputs=len(results))
    allowed_offsets = {1, 3, 7}
    for r in results:
        if r.error or r.session is None:
            continue
        session: RevisionSession = r.session
        q.schema_valid += 1
        if session.needs_human_review:
            q.gate_flag_set += 1
        item = title_to_item.get(r.title)
        selected_set = set(item.weak_topics) if item and item.weak_topics else set()
        if item is not None:
            allowed = set(FlashcardAgent.extract_topics(item.content))
            topics = {i.topic for i in session.items}
            if topics.issubset(allowed):
                q.grounded += 1
            if selected_set and selected_set.issubset(topics):
                q.covers_all_selected += 1
        # Spaced repetition offsets: next - session date in days.
        ok_offsets = True
        for i in session.items:
            delta = (i.next_revision_date - session.session_date).days
            if delta not in allowed_offsets:
                ok_offsets = False
                break
        if ok_offsets:
            q.spaced_repetition_offsets_valid += 1
    return q


def benchmark_quality(
    report: BatchReport,
    dataset: list[DemoDatasetItem] | None = None,
    *,
    expected_card_format: str = "term-definition",
    expected_card_count: int = 5,
) -> BenchmarkReport:
    """Run the full benchmark against a batch report + demo dataset.

    Args:
        report: Output from :func:`~src.study.batch.run_full_batch`.
        dataset: Demo dataset used to produce the report. Defaults to
            :func:`~src.study.batch.default_demo_dataset`.
        expected_card_format: Expected format for the flashcard run.
        expected_card_count: Expected number of cards per dataset row.

    Returns:
        A :class:`BenchmarkReport` with deterministic per-agent and overall
        quality scores, serialisable via :meth:`BenchmarkReport.to_dict`.
    """
    dataset = dataset or default_demo_dataset()
    return BenchmarkReport(
        flashcards=_evaluate_flashcards(
            report.flashcards,
            dataset,
            expected_format=expected_card_format,
            expected_count=expected_card_count,
        ),
        plans=_evaluate_plans(report.plans, dataset),
        revisions=_evaluate_revisions(report.revisions, dataset),
    )
