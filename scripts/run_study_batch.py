from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.study.batch import run_full_batch
from src.study.evaluation import benchmark_quality


def main() -> None:
    report = run_full_batch(card_count=5, card_format="term-definition")
    benchmark = benchmark_quality(
        report, expected_card_count=5, expected_card_format="term-definition"
    )
    print("BATCH_SUMMARY", json.dumps(report.summary(), indent=2, sort_keys=True))
    print("BENCHMARK", json.dumps(benchmark.to_dict(), indent=2, sort_keys=True))
    print("FLASHCARD_COUNTS", [len(r.card_set.cards) for r in report.flashcards])
    print(
        "FLASHCARD_FORMATS",
        [sorted({c.format for c in r.card_set.cards}) for r in report.flashcards],
    )
    sample_flashcards = report.flashcards[0].card_set
    sample_plan = report.plans[0].plan
    sample_revision = report.revisions[0].session
    print("SAMPLE_FLASHCARD_NEEDS_REVIEW", sample_flashcards.needs_human_review)
    print("SAMPLE_FLASHCARD_TOPICS", [c.source_topic for c in sample_flashcards.cards])
    if sample_plan is not None:
        print("SAMPLE_PLAN_NEEDS_REVIEW", sample_plan.needs_human_review)
        print("SAMPLE_PLAN_GOAL", sample_plan.goal)
        print("SAMPLE_PLAN_TOPICS", [s.topic for s in sample_plan.topic_schedule])
    if sample_revision is not None:
        print("SAMPLE_REVISION_NEEDS_REVIEW", sample_revision.needs_human_review)
        print("SAMPLE_REVISION_TOPICS", [i.topic for i in sample_revision.items])
        print(
            "SAMPLE_REVISION_OFFSETS",
            [
                (i.next_revision_date - sample_revision.session_date).days
                for i in sample_revision.items
            ],
        )


if __name__ == "__main__":
    main()
