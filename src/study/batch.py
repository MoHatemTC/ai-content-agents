"""Batch generation across a demo dataset.

This module powers the demo workflow: given a list of ``(title, content)``
pairs - the "demo dataset" - it runs each study-lane agent on every entry
and collects the outputs into an auditable batch report.

The outputs remain **pending human review** (``needs_human_review=True``)
and are never exported from this module; the caller is responsible for
feeding each batch item through the review gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.schemas import FlashcardSet
from src.study.flashcard_agent import FlashcardAgent
from src.study.revision_agent import RevisionAgent
from src.study.schemas import RevisionSession, StudyPlan
from src.study.study_plan_agent import StudyPlanAgent

logger = logging.getLogger(__name__)


@dataclass
class DemoDatasetItem:
    """One row of the demo dataset."""

    title: str
    content: str
    learner_goal: str = "Understand the material"
    difficulty: str = "medium"
    hours_per_week: float | None = 10.0
    start_date: date | None = None
    end_date: date | None = None
    weak_topics: list[str] | None = None


@dataclass
class BatchFlashcardResult:
    title: str
    card_set: FlashcardSet
    error: str | None = None


@dataclass
class BatchPlanResult:
    title: str
    plan: StudyPlan | None
    error: str | None = None


@dataclass
class BatchRevisionResult:
    title: str
    session: RevisionSession | None
    error: str | None = None


@dataclass
class BatchReport:
    """Aggregate batch-run report used by the evaluation module."""

    flashcards: list[BatchFlashcardResult] = field(default_factory=list)
    plans: list[BatchPlanResult] = field(default_factory=list)
    revisions: list[BatchRevisionResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return counts of successes / failures per agent."""

        def _ok_count(items: list[Any]) -> int:
            return sum(1 for r in items if r.error is None)

        def _err_count(items: list[Any]) -> int:
            return sum(1 for r in items if r.error is not None)

        return {
            "flashcards": {
                "total": len(self.flashcards),
                "ok": _ok_count(self.flashcards),
                "errors": _err_count(self.flashcards),
            },
            "plans": {
                "total": len(self.plans),
                "ok": _ok_count(self.plans),
                "errors": _err_count(self.plans),
            },
            "revisions": {
                "total": len(self.revisions),
                "ok": _ok_count(self.revisions),
                "errors": _err_count(self.revisions),
            },
        }


def default_demo_dataset() -> list[DemoDatasetItem]:
    """Return a small, deterministic demo dataset used by CI + demo UI.

    Content strings are self-contained and deliberately include a mixture
    of proper nouns (Python, Functions, Loops, Machine Learning, Gradient
    Descent, Overfitting) so the topic extraction heuristic produces a
    stable allow-list across runs.
    """
    today = date.today()
    end = date.fromordinal(today.toordinal() + 28)

    python_content = (
        "Python is a high-level, interpreted programming language. "
        "Key concepts include Functions, Loops (for and while), Classes, "
        "Lists, Dictionaries, and Error Handling. Functions are reusable "
        "blocks defined with the def keyword. Loops iterate over sequences. "
        "Classes enable object-oriented programming. "
        "Lists and Dictionaries are core data structures. "
        "Error Handling uses try/except blocks."
    )
    ml_content = (
        "Machine Learning teaches systems to learn patterns from data. "
        "Key topics include Supervised Learning, Unsupervised Learning, "
        "Gradient Descent, Overfitting, Regularisation, Train Test Split, "
        "and Evaluation Metrics. Supervised Learning uses labelled data. "
        "Gradient Descent optimises model parameters. Overfitting occurs "
        "when the model memorises noise; Regularisation prevents it. "
        "Evaluation Metrics such as Accuracy and F1 score measure quality."
    )
    bio_content = (
        "Cell Biology fundamentals: Cells, Nucleus, Mitochondria, Ribosomes, "
        "Cell Membrane, Diffusion, Osmosis, Mitosis, and DNA Replication. "
        "The Nucleus stores genetic material. Mitochondria produce energy. "
        "Ribosomes assemble proteins. Mitosis is cell division. "
        "DNA Replication copies the genome before division. "
        "Diffusion and Osmosis describe passive transport across the Cell Membrane."
    )
    return [
        DemoDatasetItem(
            title="Python Programming Basics",
            content=python_content,
            learner_goal="Prepare for Python exam",
            difficulty="medium",
            hours_per_week=8.0,
            start_date=today,
            end_date=end,
            weak_topics=["Functions", "Classes"],
        ),
        DemoDatasetItem(
            title="Intro to Machine Learning",
            content=ml_content,
            learner_goal="Understand ML fundamentals",
            difficulty="hard",
            hours_per_week=12.0,
            start_date=today,
            end_date=end,
            weak_topics=["Gradient Descent", "Overfitting"],
        ),
        DemoDatasetItem(
            title="Cell Biology",
            content=bio_content,
            learner_goal="Pass biology quiz",
            difficulty="easy",
            hours_per_week=6.0,
            start_date=today,
            end_date=end,
            weak_topics=["Mitosis", "DNA Replication"],
        ),
    ]


def run_flashcard_batch(
    dataset: list[DemoDatasetItem],
    *,
    card_format: str = "term-definition",
    card_count: int = 5,
    agent: FlashcardAgent | None = None,
) -> list[BatchFlashcardResult]:
    """Run the flashcard agent over every row of the demo dataset.

    Calls ``generate``, not ``generate_reviewable``, and that is deliberate:
    this is the benchmark harness, and filling a reviewer's queue with three
    demo rows per agent every time somebody measures groundedness would make
    the queue useless for the thing it exists for. The pages that a learner
    actually generates from - ``src/app.py`` and ``src/study/ui.py`` - both
    persist. Do not "fix" this one to match them.

    Args:
        dataset: Rows to process.
        card_format: ``term-definition`` or ``qa``.
        card_count: Cards per row.
        agent: Optional pre-built agent. Tests inject one with a fake
            client; otherwise a live agent is built from the gateway.
    """
    agent = agent or FlashcardAgent()
    results: list[BatchFlashcardResult] = []
    for item in dataset:
        try:
            card_set = agent.generate(
                item.content,
                card_format=card_format,
                card_count=card_count,
            )
            results.append(BatchFlashcardResult(title=item.title, card_set=card_set))
        except Exception as exc:
            logger.exception("Flashcard batch failed for %r", item.title)
            results.append(
                BatchFlashcardResult(
                    title=item.title,
                    card_set=FlashcardSet(title=item.title, cards=[]),
                    error=str(exc),
                )
            )
    return results


def run_study_plan_batch(
    dataset: list[DemoDatasetItem],
    *,
    agent: StudyPlanAgent | None = None,
) -> list[BatchPlanResult]:
    """Run the study-plan agent over every row of the demo dataset."""
    agent = agent or StudyPlanAgent()
    today = date.today()
    results: list[BatchPlanResult] = []
    for item in dataset:
        try:
            plan = agent.generate(
                item.content,
                learner_goal=item.learner_goal,
                difficulty=item.difficulty,
                start_date=item.start_date or today,
                end_date=item.end_date or date.fromordinal(today.toordinal() + 28),
                hours_per_week=item.hours_per_week,
            )
            results.append(BatchPlanResult(title=item.title, plan=plan))
        except Exception as exc:
            logger.exception("Plan batch failed for %r", item.title)
            results.append(BatchPlanResult(title=item.title, plan=None, error=str(exc)))
    return results


def run_revision_batch(
    dataset: list[DemoDatasetItem],
    *,
    agent: RevisionAgent | None = None,
) -> list[BatchRevisionResult]:
    """Run the revision agent over every row of the demo dataset.

    Falls back to the first 2 extracted topics when ``item.weak_topics``
    is empty, to guarantee an output.
    """
    agent = agent or RevisionAgent()
    today = date.today()
    results: list[BatchRevisionResult] = []
    for item in dataset:
        try:
            weak_topics = item.weak_topics
            if not weak_topics:
                extracted = FlashcardAgent.extract_topics(item.content)
                weak_topics = extracted[:2] if extracted else ["General topic"]
            session = agent.generate(
                item.content,
                selected_topics=weak_topics,
                session_date=today,
            )
            results.append(BatchRevisionResult(title=item.title, session=session))
        except Exception as exc:
            logger.exception("Revision batch failed for %r", item.title)
            results.append(
                BatchRevisionResult(title=item.title, session=None, error=str(exc))
            )
    return results


def run_full_batch(
    dataset: list[DemoDatasetItem] | None = None,
    *,
    card_format: str = "term-definition",
    card_count: int = 5,
    agents: tuple[FlashcardAgent, StudyPlanAgent, RevisionAgent] | None = None,
) -> BatchReport:
    """Run all three agents across the demo dataset; return a BatchReport."""
    dataset = dataset or default_demo_dataset()
    if agents is None:
        fc, sp, rv = FlashcardAgent(), StudyPlanAgent(), RevisionAgent()
    else:
        fc, sp, rv = agents
    report = BatchReport()
    report.flashcards = run_flashcard_batch(
        dataset, card_format=card_format, card_count=card_count, agent=fc
    )
    report.plans = run_study_plan_batch(dataset, agent=sp)
    report.revisions = run_revision_batch(dataset, agent=rv)
    return report
