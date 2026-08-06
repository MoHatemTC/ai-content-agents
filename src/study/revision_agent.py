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
from src.study.schemas import RevisionItem, RevisionSession

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
        mock_mode: When ``True``, return deterministic grounded samples.
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
                    "LITELLM_API_KEY and LITELLM_BASE_URL required in live mode."
                )
            from openai import OpenAI  # type: ignore

            self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")
            self.client: Any = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        else:
            self.client = None
            self.model = None

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
        template = self.prompt_cfg.get("system_prompt")
        if not template:
            raise KeyError("'system_prompt' missing in revision.yaml")
        extracted_json = json.dumps(extracted_topics, ensure_ascii=False)
        selected_json = json.dumps(selected_topics, ensure_ascii=False)
        return (
            f"{template}\n\n"
            f"extracted_topics (full allow-list): {extracted_json}\n"
            f"selected_topics (subset to revise): {selected_json}\n"
            f"session_date: {session_date.isoformat()}\n"
            # The YAML names the schema but never sends it; without the shape
            # the model omits required keys and validation fails.
            f"{schema_block(RevisionSession)}"
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
        selected_topics: list[str],
        session_date: date,
    ) -> RevisionSession:
        items: list[RevisionItem] = []
        for t in selected_topics:
            difficulty = RevisionAgent._pick_difficulty(
                t, "\n".join(extracted_topics + selected_topics)
            )
            offset = _DIFFICULTY_OFFSETS[difficulty]
            items.append(
                RevisionItem(
                    topic=t,
                    description=(
                        f"Revise {t} using active recall. Cover definitions, "
                        f"examples, and common pitfalls."
                    ),
                    next_revision_date=session_date + timedelta(days=offset),
                    difficulty=difficulty,
                    confidence_prompt=(
                        f"On a 1-5 scale, how confident are you about {t}?"
                    ),
                    source_chunk_id=None,
                )
            )
        return RevisionSession(
            session_date=session_date,
            items=items,
            notes=(
                "Generated revision session. "
                "Apply human review before scheduling on a calendar."
            ),
            selected_weak_topics=sorted(selected_topics),
            source_topics=sorted(selected_topics),
            needs_human_review=True,
        )

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

    def _wrap_for_review_gate(
        self, session: RevisionSession, *, run_id: str
    ) -> RevisionSession:
        source_topics = sorted({i.topic for i in session.items})
        return RevisionSession(
            session_date=session.session_date,
            items=session.items,
            notes=(session.notes or "") + f" [run_id={run_id} pending_review]",
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
        run_id = f"rv-{uuid4().hex[:8]}"

        extracted_topics = FlashcardAgent.extract_topics(content)
        # Fall back if heuristic yielded nothing for very short content
        extracted_topics = extracted_topics or list(dict.fromkeys(selected_topics))

        invalid_selected = [
            t for t in selected_topics if t not in set(extracted_topics)
        ]
        if invalid_selected:
            raise RevisionGroundingError(
                "selected_topics reference content topics that were not "
                f"extracted from the content: {invalid_selected!r}. "
                f"Extracted allow-list: {sorted(extracted_topics)}"
            )

        prompt = self._build_prompt(extracted_topics, selected_topics, sdate)
        if self.mock_mode:
            raw = self._mock_response(extracted_topics, selected_topics, sdate)
        else:  # pragma: no cover - live path
            try:
                text = self._call_llm(prompt, output_budget(len(selected_topics)))
            except UpstreamResponseError:
                logger.exception("Revision LLM call failed")
                raise
            raw = parse_json(text, RevisionSession)

        self._validate_revision(raw, extracted_topics, selected_topics)
        return self._wrap_for_review_gate(raw, run_id=run_id)
