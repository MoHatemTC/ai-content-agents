"""Study Plan agent: grounded plan built from real content topics + goals.

Like the flashcard agent, the planner does not trust the LLM to stay within
topic bounds. A deterministic pre-extraction step produces a strict
``extracted_topics`` allow-list (reusing :meth:`FlashcardAgent.extract_topics`
from the sibling module), every TopicSchedule is then re-validated against
that list at the output, and the returned plan is explicitly marked
``needs_human_review=True``.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from dotenv import load_dotenv

from src.study.flashcard_agent import FlashcardAgent
from src.study.llm_client import (
    UpstreamResponseError,
    call_llm,
    output_budget,
    parse_json,
    schema_block,
)
from src.study.schemas import StudyPlan, TopicSchedule

load_dotenv()
logger = logging.getLogger(__name__)


class PlanGroundingError(ValueError):
    """Raised when a plan schedules a topic not in the content allow-list."""


class StudyPlanAgent:
    """Grounded study-plan generator.

    Args:
        mock_mode: When ``True``, bypass LiteLLM and return a deterministic
            sample plan grounded in the extraction allow-list.
    """

    def __init__(self, mock_mode: bool | None = None) -> None:
        if mock_mode is None:
            self.mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true"
        else:
            self.mock_mode = mock_mode

        self.prompt_cfg = self._load_prompt()

        if not self.mock_mode:
            api_key = os.getenv("LITELLM_API_KEY")
            base_url = os.getenv("LITELLM_BASE_URL")
            if not api_key or not base_url:
                raise ValueError(
                    "LITELLM_API_KEY and LITELLM_BASE_URL are required in live mode."
                )
            from openai import OpenAI  # type: ignore

            self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")
            self.client: Any = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        else:
            self.client = None
            self.model = None

    # ------------------------------------------------------------------
    # Prompt / extraction helpers
    # ------------------------------------------------------------------

    def _load_prompt(self) -> dict[str, Any]:
        path = Path(__file__).resolve().parent / "prompts" / "study_plan.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt missing: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:  # pragma: no cover
            raise ValueError("Invalid YAML in study_plan.yaml") from exc
        if data is None:
            raise ValueError("study_plan.yaml is empty")
        if not isinstance(data, dict):
            raise TypeError("study_plan.yaml must be a dict")
        return data

    @staticmethod
    def _parse_date(value: date | str) -> date:
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    def _build_prompt(
        self,
        extracted_topics: list[str],
        learner_goal: str,
        difficulty: str,
        start_date: date,
        end_date: date,
        hours_per_week: float | None,
    ) -> str:
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(f"difficulty must be easy/medium/hard, got {difficulty!r}")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        template = self.prompt_cfg.get("system_prompt")
        if not template:
            raise KeyError("'system_prompt' missing in study_plan.yaml")

        topics_json = json.dumps(extracted_topics, ensure_ascii=False)
        return (
            f"{template}\n\n"
            f"extracted_topics (schedule ONLY from this list): {topics_json}\n"
            f"learner_goal: {learner_goal}\n"
            f"difficulty: {difficulty}\n"
            f"start_date: {start_date.isoformat()}\n"
            f"end_date: {end_date.isoformat()}\n"
            f"hours_per_week: {hours_per_week if hours_per_week else 'unspecified'}\n"
            # The YAML names the schema but never sends it; without the shape
            # the model omits required keys and validation fails.
            f"{schema_block(StudyPlan)}"
        )

    # ------------------------------------------------------------------
    # LLM / mock
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int | None = None) -> str:
        """Send the prompt to the gateway and return the reply body."""
        return call_llm(
            self.client, self.model, prompt, max_tokens=max_tokens
        )

    @staticmethod
    def _mock_response(
        extracted_topics: list[str],
        learner_goal: str,
        difficulty: str,
        start_date: date,
        end_date: date,
        hours_per_week: float | None,
    ) -> StudyPlan:
        """Deterministic grounded sample plan for tests and demoing."""
        topics = extracted_topics or ["General topic"]
        total_days = max(1, (end_date - start_date).days)
        days_per_topic = max(1, total_days // len(topics))
        schedule: list[TopicSchedule] = []
        weekly_budget = hours_per_week if hours_per_week else 10.0
        total_weeks = max(1, total_days / 7.0)
        total_budget_hours = weekly_budget * total_weeks
        per_topic = max(0.5, total_budget_hours / len(topics))

        for i, t in enumerate(topics):
            t_start = start_date + timedelta(days=i * days_per_topic)
            t_end = min(end_date, t_start + timedelta(days=days_per_topic - 1))
            if t_end < t_start:
                t_end = t_start
            schedule.append(
                TopicSchedule(
                    topic=t,
                    start_date=t_start,
                    end_date=t_end,
                    duration_hours=round(per_topic, 2),
                    difficulty=difficulty,
                    resources=[f"Content section: {t}"],
                )
            )
        return StudyPlan(
            goal=learner_goal or "Master the content topics",
            start_date=start_date,
            end_date=end_date,
            overall_difficulty=difficulty,
            available_hours_per_week=hours_per_week,
            topic_schedule=schedule,
            source_topics=sorted(topics),
            needs_human_review=True,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_plan(
        self, plan: StudyPlan, extracted_topics: list[str]
    ) -> None:
        """Validate topic membership, dates, and difficulty values.

        Raises:
            PlanGroundingError: If any scheduled topic is not in the allow-list.
            ValueError: If any structural rule (dates, difficulty) is broken.
        """
        allowed = set(extracted_topics)
        bad_topics = [
            s.topic for s in plan.topic_schedule if s.topic not in allowed
        ]
        if bad_topics:
            raise PlanGroundingError(
                "Plan schedules topics not in extraction allow-list: "
                f"{bad_topics!r}; allowed={sorted(allowed)}"
            )

        if plan.start_date > plan.end_date:
            raise ValueError("Plan start_date must be <= end_date")

        if plan.overall_difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(
                f"overall_difficulty invalid: {plan.overall_difficulty!r}"
            )

        for s in plan.topic_schedule:
            if s.start_date > s.end_date:
                raise ValueError(f"Topic schedule invalid dates: {s.topic}")
            if s.start_date < plan.start_date or s.end_date > plan.end_date:
                raise ValueError(
                    f"Topic schedule outside plan window: {s.topic}"
                )
            if s.difficulty not in {"easy", "medium", "hard"}:
                raise ValueError(
                    f"Topic schedule difficulty invalid: {s.topic} -> {s.difficulty!r}"
                )
            if s.duration_hours <= 0:
                raise ValueError(
                    f"Topic schedule duration_hours must be > 0: {s.topic}"
                )

    def _wrap_for_review_gate(self, plan: StudyPlan, *, run_id: str) -> StudyPlan:
        source_topics = sorted({s.topic for s in plan.topic_schedule})
        return StudyPlan(
            goal=plan.goal,
            start_date=plan.start_date,
            end_date=plan.end_date,
            overall_difficulty=plan.overall_difficulty,
            available_hours_per_week=plan.available_hours_per_week,
            topic_schedule=plan.topic_schedule,
            source_topics=source_topics,
            needs_human_review=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        content: str,
        *,
        learner_goal: str,
        difficulty: str = "medium",
        start_date: date | str,
        end_date: date | str,
        hours_per_week: float | None = None,
    ) -> StudyPlan:
        """Build a grounded study plan from real content topics + goals.

        Args:
            content: Clean study material (used to extract topic allow-list).
            learner_goal: Learner-stated goal (free text).
            difficulty: Overall plan difficulty: easy/medium/hard.
            start_date: Plan window start (ISO string or date).
            end_date: Plan window end.
            hours_per_week: Optional weekly study budget; when provided,
                the planner distributes topic hours within this budget.

        Returns:
            Validated :class:`StudyPlan` with ``needs_human_review=True``.
            Always route through the shared review gate before exporting.

        Raises:
            ValueError: On invalid inputs or structural rule violations.
            PlanGroundingError: If the plan references out-of-list topics.
        """
        if not content or not content.strip():
            raise ValueError("content is empty; cannot build plan")
        sd = self._parse_date(start_date)
        ed = self._parse_date(end_date)
        run_id = f"sp-{uuid4().hex[:8]}"
        extracted_topics = FlashcardAgent.extract_topics(content)
        if not extracted_topics:
            extracted_topics = [
                learner_goal.strip() or "General learning content"
            ]

        prompt = self._build_prompt(
            extracted_topics, learner_goal, difficulty, sd, ed, hours_per_week
        )

        if self.mock_mode:
            raw = self._mock_response(
                extracted_topics, learner_goal, difficulty, sd, ed, hours_per_week
            )
        else:  # pragma: no cover - live path
            try:
                text = self._call_llm(prompt, output_budget(len(extracted_topics)))
            except UpstreamResponseError:
                logger.exception("Study plan LLM call failed")
                raise
            raw = parse_json(text, StudyPlan)

        self._validate_plan(raw, extracted_topics)
        return self._wrap_for_review_gate(raw, run_id=run_id)
