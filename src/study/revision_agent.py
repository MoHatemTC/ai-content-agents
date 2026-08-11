"""Revision Assistant agent: targeted revision items from weak/selected topics.

The revision agent takes a list of user-selected *weak topics* and produces
one grounded :class:`RevisionItem` per topic using a spaced-repetition
heuristic (easy=+7d, medium=+3d, hard=+1d). As with the other study-lane
agents:

* A strict topic allow-list is deterministically extracted from the content.
* Every ``selected_topic`` must be a subset of that allow-list, otherwise
  the call raises.
* The returned :class:`RevisionSession` is always marked
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
from src.study.schemas import RevisionSession

load_dotenv()
logger = logging.getLogger(__name__)

_DIFFICULTY_OFFSETS: dict[str, int] = {
    "easy": 7,
    "medium": 3,
    "hard": 1,
}


class RevisionGroundingError(ValueError):
    """Raised when revision topics are not in the content allow-list."""


class RevisionAgent:
    """Grounded revision-session generator.

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
    # Helpers
    # ------------------------------------------------------------------

    def _load_prompt(self) -> dict[str, Any]:
        path = Path(__file__).resolve().parent / "prompts" / "revision.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt missing: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:  # pragma: no cover
            raise ValueError("Invalid YAML in revision.yaml") from exc
        if data is None:
            raise ValueError("revision.yaml is empty")
        if not isinstance(data, dict):
            raise TypeError("revision.yaml must be a dict")
        return data

    @staticmethod
    def _parse_date(value: date | str) -> date:
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    @staticmethod
    def _pick_difficulty(topic: str, content: str) -> str:
        """Heuristic: topic mentioned fewer times => harder."""
        count = content.lower().count(topic.lower())
        if count >= 3:
            return "easy"
        if count == 2:
            return "medium"
        return "hard"

    def _build_prompt(
        self,
        extracted_topics: list[str],
        selected_topics: list[str],
        session_date: date,
    ) -> str:
        template = self.prompt_cfg.get("prompt_template")
        if not template:
            raise KeyError("'prompt_template' missing in revision.yaml")

        rendered = template.format(
            extracted_topics=json.dumps(extracted_topics, ensure_ascii=False),
            selected_topics=json.dumps(selected_topics, ensure_ascii=False),
            session_date=session_date.isoformat(),
        )
        # The literal example in the YAML shows the shape; this appends the
        # generated JSON schema too. Without one or the other the model omits
        # required keys and validation fails.
        return f"{rendered}{schema_block(RevisionSession)}"

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int | None = None) -> str:
        """Send the prompt to the gateway and return the reply body."""
        return call_llm(self.client, self.model, prompt, max_tokens=max_tokens)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_revision(
        self,
        session: RevisionSession,
        extracted_topics: list[str],
        selected_topics: list[str],
    ) -> None:
        allowed = set(extracted_topics)
        allowed_selected = set(selected_topics) & allowed
        bad = [i.topic for i in session.items if i.topic not in allowed_selected]
        if bad:
            raise RevisionGroundingError(
                "Revision topics not in allow-list+selected intersection: "
                f"{bad!r}; selected&allowed={sorted(allowed_selected)}"
            )
        for i in session.items:
            if i.difficulty not in _DIFFICULTY_OFFSETS:
                raise ValueError(
                    f"Invalid difficulty for {i.topic!r}: {i.difficulty!r}"
                )
            if i.next_revision_date < session.session_date:
                raise ValueError(
                    f"next_revision_date before session_date for {i.topic!r}"
                )

    def _wrap_for_review_gate(self, session: RevisionSession) -> RevisionSession:
        """Force the review-gate flags and normalise.

        The run id used to be appended to ``notes``, which app.py renders as a
        caption under the session - so the learner read it. It lives on the
        persisted AgentRun now.
        """
        source_topics = sorted({i.topic for i in session.items})
        return RevisionSession(
            session_date=session.session_date,
            items=session.items,
            notes=session.notes,
            selected_weak_topics=sorted(session.selected_weak_topics or source_topics),
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
        selected_topics: list[str],
        session_date: date | str,
        extracted_topics: list[str] | None = None,
    ) -> RevisionSession:
        """Produce targeted revision items for the selected weak topics.

        Args:
            content: Clean study material; used to extract the topic
                allow-list and to validate selected_topics.
            selected_topics: Weak/selected topics the user wants to revise.
                Each topic must be in the extraction allow-list (a
                deterministic substring of ``content``) otherwise the call
                raises.
            session_date: ISO date/date for the session.
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
            Validated :class:`RevisionSession` marked
            ``needs_human_review=True``. Always route through the shared
            review gate before exporting.

        Raises:
            RevisionGroundingError: If any selected_topic is not in the
                content-derived allow-list.
            ValueError: On invalid inputs.
        """
        if not content or not content.strip():
            raise ValueError("content is empty; cannot build revision items")
        if not selected_topics:
            raise ValueError("selected_topics cannot be empty")

        sdate = self._parse_date(session_date)

        if extracted_topics is None:
            extracted_topics = FlashcardAgent.extract_topics(content)
        # Fall back if heuristic yielded nothing for very short content
        extracted_topics = extracted_topics or list(dict.fromkeys(selected_topics))

        canonical_selected: list[str] = []
        invalid_selected: list[str] = []
        for topic in selected_topics:
            canonical = FlashcardAgent.canonical_topic(topic, extracted_topics)
            if canonical is None:
                invalid_selected.append(topic)
            else:
                canonical_selected.append(canonical)
        if invalid_selected:
            raise RevisionGroundingError(
                "selected_topics reference content topics that were not "
                f"extracted from the content: {invalid_selected!r}. "
                f"Extracted allow-list: {sorted(extracted_topics)}"
            )

        selected_topics = canonical_selected
        prompt = self._build_prompt(extracted_topics, selected_topics, sdate)
        try:
            text = self._call_llm(prompt, output_budget(len(selected_topics)))
        except UpstreamResponseError:
            logger.exception("Revision LLM call failed")
            raise
        raw = parse_json(text, RevisionSession)

        self._validate_revision(raw, extracted_topics, selected_topics)
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
        "pending review" while the reviewer's queue stayed empty, so a revision session
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
            agent_name="revision_agent",
            output_type="revision_session",
            output_schema=RevisionSession,
            model=self.model,
            input_context=content,
            source_chunk_ids=source_chunk_ids,
            generate=lambda: self.generate(
                content,
                **kwargs,
            ),
        )
