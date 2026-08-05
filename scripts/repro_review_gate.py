from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.study.batch import default_demo_dataset
from src.study.flashcard_agent import FlashcardAgent
from src.validation.review_schema import (
    GeneratedOutput,
    OutputStatus,
    ReviewAction,
    assert_exportable,
    apply_review,
)


def main() -> None:
    item = default_demo_dataset()[0]
    flashcards = FlashcardAgent(mock_mode=True).generate(
        item.content, card_format="term-definition", card_count=5
    )
    print("MODEL_NEEDS_REVIEW", flashcards.needs_human_review)

    output = GeneratedOutput(
        agent_run_id="demo-run",
        output_type="flashcards",
        payload=flashcards.model_dump(),
        schema_name="FlashcardSet",
        validation_passed=True,
        validation_report={},
        status=OutputStatus.PENDING,
    )

    try:
        assert_exportable(output)
        print("FAIL: export gate should have blocked pending output")
    except Exception as exc:
        print("PASS: export gate blocks pending output", type(exc).__name__)

    apply_review(output, reviewer="tester", action=ReviewAction.APPROVE)
    assert_exportable(output)
    print("PASS: export gate allows approved output", output.status.value)


if __name__ == "__main__":
    main()
