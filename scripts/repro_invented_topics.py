from __future__ import annotations

from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.schemas import Flashcard, FlashcardSet
from src.study.batch import default_demo_dataset
from src.study.flashcard_agent import FlashcardAgent, GroundingError
from src.study.revision_agent import RevisionAgent, RevisionGroundingError
from src.study.schemas import StudyPlan, TopicSchedule
from src.study.study_plan_agent import PlanGroundingError, StudyPlanAgent


def _print_result(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    line = f"{status}: {name}"
    if detail:
        line += f" :: {detail}"
    print(line)


def flashcards_invented_topic_should_raise() -> None:
    item = default_demo_dataset()[0]
    agent = FlashcardAgent(mock_mode=True)

    def bad_mock_response(
        extracted_topics: list[str], card_format: str, card_count: int
    ) -> FlashcardSet:
        return FlashcardSet(
            title="Bad flashcards",
            description="Contains invented topic",
            cards=[
                Flashcard(
                    front="Invented",
                    back="Invented",
                    format=card_format,
                    source_topic="INVENTED_TOPIC",
                    source_chunk_id=None,
                    tags=["bad"],
                )
            ],
            source_topics=["INVENTED_TOPIC"],
            source_chunk_ids=[],
            needs_human_review=True,
        )

    agent._mock_response = staticmethod(bad_mock_response)  # type: ignore[method-assign]

    try:
        agent.generate(item.content, card_format="term-definition", card_count=3)
    except GroundingError as exc:
        _print_result(
            "Flashcards invented topic blocked", True, str(exc).splitlines()[0]
        )
        return
    _print_result(
        "Flashcards invented topic blocked", False, "No GroundingError raised"
    )


def plan_invented_topic_should_raise() -> None:
    item = default_demo_dataset()[0]
    agent = StudyPlanAgent(mock_mode=True)
    start = date.today()
    end = date.fromordinal(start.toordinal() + 7)

    def bad_mock_plan(
        extracted_topics: list[str],
        learner_goal: str,
        difficulty: str,
        start_date: date,
        end_date: date,
        hours_per_week: float | None,
    ) -> StudyPlan:
        return StudyPlan(
            goal=learner_goal,
            start_date=start_date,
            end_date=end_date,
            overall_difficulty=difficulty,
            available_hours_per_week=hours_per_week,
            topic_schedule=[
                TopicSchedule(
                    topic="INVENTED_TOPIC",
                    start_date=start_date,
                    end_date=start_date,
                    duration_hours=1.0,
                    difficulty=difficulty,
                    resources=[],
                )
            ],
            source_topics=["INVENTED_TOPIC"],
            needs_human_review=True,
        )

    agent._mock_response = staticmethod(bad_mock_plan)  # type: ignore[method-assign]

    try:
        agent.generate(
            item.content,
            learner_goal="Goal",
            difficulty="easy",
            start_date=start,
            end_date=end,
            hours_per_week=5.0,
        )
    except PlanGroundingError as exc:
        _print_result(
            "Study plan invented topic blocked", True, str(exc).splitlines()[0]
        )
        return
    _print_result(
        "Study plan invented topic blocked", False, "No PlanGroundingError raised"
    )


def revision_invalid_selected_topic_should_raise() -> None:
    item = default_demo_dataset()[0]
    agent = RevisionAgent(mock_mode=True)
    try:
        agent.generate(
            item.content, selected_topics=["INVENTED_TOPIC"], session_date=date.today()
        )
    except RevisionGroundingError as exc:
        _print_result(
            "Revision invalid selected topic blocked", True, str(exc).splitlines()[0]
        )
        return
    _print_result(
        "Revision invalid selected topic blocked",
        False,
        "No RevisionGroundingError raised",
    )


def main() -> None:
    flashcards_invented_topic_should_raise()
    plan_invented_topic_should_raise()
    revision_invalid_selected_topic_should_raise()


if __name__ == "__main__":
    main()
