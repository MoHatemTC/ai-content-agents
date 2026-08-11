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
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.validation.review_schema import GeneratedOutput
from src.validation.reviewable import persist_reviewable_run
from src.llm_gateway import build_client, default_model
from src.study.flashcard_agent import FlashcardAgent
from src.study.llm_client import (
    UpstreamResponseError,
    call_llm,
    output_budget,
    parse_json,
    schema_block,
)
from src.study.schemas import StudyPlan

load_dotenv()
logger = logging.getLogger(__name__)


class PlanGroundingError(ValueError):
    """Raised when a plan schedules a topic not in the content allow-list."""


class StudyPlanAgent:
    """Grounded study-plan generator.

    Args:
        client: An OpenAI-compatible client. Defaults to one built from the
            configured gateway; tests inject a double. There is no mode flag -
            see :mod:`src.llm_gateway` for why.
        model: Model id. Defaults to :func:`~src.llm_gateway.default_model`.
    """

    def __init__(self, *, client: Any | None = None, model: str | None = None) -> None:
        self.prompt_cfg = self._load_prompt()
        self.client: Any = client if client is not None else build_client()
        self.model = model or default_model()

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

        template = self.prompt_cfg.get("prompt_template")
        if not template:
            raise KeyError("'prompt_template' missing in study_plan.yaml")

        rendered = template.format(
            extracted_topics=json.dumps(extracted_topics, ensure_ascii=False),
            learner_goal=learner_goal,
            difficulty=difficulty,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            hours_per_week=hours_per_week if hours_per_week else "unspecified",
        )
        # The literal example in the YAML shows the shape; this appends the
        # generated JSON schema too. Without one or the other the model omits
        # required keys and validation fails.
        return f"{rendered}{schema_block(StudyPlan)}"

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int | None = None) -> str:
        """Send the prompt to the gateway and return the reply body."""
        return call_llm(
            self.client, self.model, prompt, max_tokens=max_tokens
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
        bad_topics: list[str] = []
        for entry in plan.topic_schedule:
            canonical = FlashcardAgent.canonical_topic(entry.topic, extracted_topics)
            if canonical is None:
                bad_topics.append(entry.topic)
            else:
                entry.topic = canonical
        if bad_topics:
            raise PlanGroundingError(
                "Plan schedules topics not in extraction allow-list: "
                f"{bad_topics!r}; allowed={sorted(extracted_topics)}"
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

    def _wrap_for_review_gate(self, plan: StudyPlan) -> StudyPlan:
        """Force the review-gate flags and normalise.

        This took a ``run_id`` and never used it, so the plan agent had no audit
        trail at all and the signature promised one. generate_reviewable records
        the run properly.
        """
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
        extracted_topics: list[str] | None = None,
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
            extracted_topics: The allow-list the caller already showed the
                learner. Defaults to deriving it from ``content``.

                Passing it is what keeps the two ends honest. The pages build
                their widgets from ``extract_topics(doc.content)`` and then
                hand the agent the *retrieved* passages, so the agent derived a
                different, smaller list and rejected topics its own page had
                just offered. Live: picking "Radiation" raised
                ``selected_topics reference content topics that were not
                extracted``. One extraction, supplied by whoever owns the
                widget, cannot disagree with itself.

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
        if extracted_topics is None:
            extracted_topics = FlashcardAgent.extract_topics(content)
        if not extracted_topics:
            extracted_topics = [
                learner_goal.strip() or "General learning content"
            ]

        prompt = self._build_prompt(
            extracted_topics, learner_goal, difficulty, sd, ed, hours_per_week
        )

        try:
            text = self._call_llm(prompt, output_budget(len(extracted_topics)))
        except UpstreamResponseError:
            logger.exception("Study plan LLM call failed")
            raise
        raw = parse_json(text, StudyPlan)

        self._validate_plan(raw, extracted_topics)
        return self._wrap_for_review_gate(raw)

    def generate_reviewable(
        self,
        content: str,
        *,
        store: Any | None = None,
        source_chunk_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> GeneratedOutput:
        """Generate and queue the result for human review.

        **This lane persisted nothing.** Every study agent set
        ``needs_human_review=True`` and its docstring told the caller to route
        the result through :mod:`src.validation.review_schema` - and no caller
        ever did, in app.py, in study/ui.py or in study/batch.py. The pages said
        "pending review" while the reviewer's queue stayed empty, so a study plan
        could never be approved, and never reached the export gate that
        :func:`~src.validation.review_schema.assert_exportable` guards.

        Args:
            content: Cleaned study material.
            store: Where to persist. Defaults to the shared
                :class:`~src.validation.store.PlatformStore`; tests inject one.
            source_chunk_ids: Provenance from ingestion, when the caller has it.
            **kwargs: Passed through to :meth:`generate`.

        Returns:
            The persisted :class:`GeneratedOutput`, pending review.
        """
        return persist_reviewable_run(
            store=store,
            agent_name="study_plan_agent",
            output_type="study_plan",
            output_schema=StudyPlan,
            model=self.model,
            input_context=content,
            source_chunk_ids=source_chunk_ids,
            generate=lambda: self.generate(
                content,
                **kwargs,
            ),
        )
