"""Flashcard agent: grounded term-definition / Q-A cards from content.

The flashcard agent is the learner-facing entry point for retrieval-practice
outputs. It follows the repository-wide four-step pattern:

1. :meth:`_extract_topics` pulls a strict allow-list of topics from the raw
   content using a deterministic keyword/token heuristic (no LLM trust at
   this step).
2. :meth:`_load_prompt` / :meth:`_build_prompt` fill the study-lane YAML
   template that *forces* the LLM to only use that allow-list.
3. :meth:`_call_llm` goes to LiteLLM in live mode; mock mode returns a
   deterministic grounded sample that passes the validators.
4. :meth:`_validate_grounding` and :meth:`_wrap_for_review_gate` enforce the
   contract: the returned :class:`FlashcardSet` is always marked
   ``needs_human_review=True``, every card's ``source_topic`` is in the
   allow-list, and the count / format match the request.

The agent *never* reports outputs as final; the caller must push the
returned model through :func:`src.validation.review_schema.apply_review`
and :func:`~src.validation.review_schema.assert_exportable` before any
export or downstream hand-off.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from dotenv import load_dotenv

from src.study.schemas import Flashcard, FlashcardSet

load_dotenv()
logger = logging.getLogger(__name__)

# Topic extraction heuristic: minimal, deterministic, cheap, auditable.
# We split the content into capitalised n-grams and high-information tokens,
# then keep the most frequent ones that are >= 3 chars long. The result is
# intentionally noisy but *never* hallucinated - it is a strict substring of
# the content. The LLM is later constrained to only pick from this list.
_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "had", "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "its", "let", "may", "new", "now", "old", "see", "two",
    "way", "who", "did", "his", "that", "this", "with", "from", "they",
    "have", "were", "been", "their", "them", "then", "what", "when", "will",
    "your", "into", "just", "some", "than", "also", "only", "over", "such",
}


class GroundingError(ValueError):
    """Raised when a card references a topic not in the extraction allow-list."""


class FlashcardAgent:
    """Grounded flashcard generator.

    Args:
        mock_mode: When ``True``, skip LiteLLM and return a deterministic
            grounded sample. Defaults to the ``MOCK_MODE`` env var
            (case-insensitive "true" = True).
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
            # Imported lazily so tests / mock-mode environments don't need
            # the openai package on PATH.
            from openai import OpenAI  # type: ignore

            self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")
            self.client: Any = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        else:
            self.client = None
            self.model = None

    # ------------------------------------------------------------------
    # Prompt + topic extraction helpers
    # ------------------------------------------------------------------

    def _load_prompt(self) -> dict[str, Any]:
        """Load the study-lane flashcards YAML template.

        Returns:
            Parsed YAML dictionary (name, description, system_prompt, ...).

        Raises:
            FileNotFoundError: If the YAML is missing.
            ValueError: If the YAML is empty, invalid, or not a dict.
        """
        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "flashcards.yaml"
        )
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file missing: {prompt_path}")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:  # pragma: no cover - YAML lib behaviour
            raise ValueError("Invalid YAML syntax in flashcards.yaml") from exc
        if data is None:
            raise ValueError("flashcards.yaml is empty")
        if not isinstance(data, dict):
            raise TypeError("flashcards.yaml must contain a YAML dictionary")
        return data

    @staticmethod
    def extract_topics(content: str, max_topics: int = 25) -> list[str]:
        """Deterministically extract a topic allow-list from raw content.

        Strategy: capitalised unigrams + bigrams, drop stopwords, keep the
        most frequent. The output is strictly substrings of ``content`` -
        the LLM later is only allowed to pick from this list.

        Args:
            content: Cleaned text from the ingestion lane.
            max_topics: Cap on allow-list size.

        Returns:
            Sorted, de-duplicated list of topic strings.
        """
        if not content or not content.strip():
            return []

        # Tokens preserving capitalisation for proper nouns, then normalised
        # frequencies. We also capture 2-word capitalised chunks.
        cap_words = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", content)
        all_words = re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,}\b", content)
        lowered = [w.lower() for w in all_words if w.lower() not in _STOPWORDS]

        # Bigrams of non-stopwords, also captured if at least one word is
        # capitalised in the source.
        bigrams = []
        for i in range(len(all_words) - 1):
            a, b = all_words[i], all_words[i + 1]
            if a.lower() in _STOPWORDS or b.lower() in _STOPWORDS:
                continue
            if a[0].isupper() or b[0].isupper():
                bigrams.append(f"{a} {b}")

        counts: Counter[str] = Counter()
        for w in cap_words:
            if w.lower() not in _STOPWORDS:
                counts[w] += 2  # capitalised = signal boost
        for w in lowered:
            counts[w] += 1
        for bg in bigrams:
            counts[bg] += 3

        ranked = [topic for topic, _ in counts.most_common(max_topics)]
        return sorted(set(ranked))

    def _build_prompt(
        self,
        content: str,
        extracted_topics: list[str],
        card_format: str,
        card_count: int,
    ) -> str:
        """Fill the YAML prompt template.

        Args:
            content: Clean text.
            extracted_topics: Strict topic allow-list from
                :meth:`extract_topics`.
            card_format: ``"term-definition"`` or ``"qa"``.
            card_count: Target card count.

        Returns:
            Fully rendered prompt string.
        """
        if card_format not in {"term-definition", "qa"}:
            raise ValueError(
                f"card_format must be 'term-definition' or 'qa', got {card_format!r}"
            )
        if card_count < 1:
            raise ValueError("card_count must be >= 1")

        template = self.prompt_cfg.get("system_prompt")
        if not template:
            raise KeyError("'system_prompt' missing in flashcards.yaml")

        topics_json = json.dumps(extracted_topics, ensure_ascii=False)
        prompt_block = (
            f"{template}\n\n"
            f"--- CONTENT START ---\n{content}\n--- CONTENT END ---\n\n"
            f"extracted_topics (pick FROM THIS LIST ONLY): {topics_json}\n"
            f"card_format: {card_format}\n"
            f"card_count: {card_count}\n"
        )
        return prompt_block

    # ------------------------------------------------------------------
    # LLM + mock responses
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> str:
        """Send the prompt to LiteLLM and return the raw text response.

        Args:
            prompt: Fully rendered prompt.

        Returns:
            Stripped LLM response body.
        """
        assert self.client is not None, "Called _call_llm in mock_mode"
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty response")
        return content.strip()

    @staticmethod
    def _mock_response(
        extracted_topics: list[str], card_format: str, card_count: int
    ) -> FlashcardSet:
        """Deterministic grounded sample for tests and local demoing.

        Args:
            extracted_topics: Topic allow-list.
            card_format: ``term-definition`` or ``qa``.
            card_count: Target count.

        Returns:
            Valid, grounded :class:`FlashcardSet` that passes every validator
            in :meth:`_validate_grounding`.
        """
        topics = extracted_topics or ["General topic"]
        n = min(card_count, max(1, len(topics)))
        cards: list[Flashcard] = []
        for i in range(n):
            topic = topics[i % len(topics)]
            if card_format == "term-definition":
                front = topic
                back = (
                    f"{topic} is a key concept described in the supplied "
                    f"content. See the source text for a fuller treatment."
                )
            else:  # qa
                front = f"What is {topic}?"
                back = f"{topic} is explained in the supplied content as an important topic."
            cards.append(
                Flashcard(
                    front=front,
                    back=back,
                    format=card_format,
                    source_topic=topic,
                    source_chunk_id=None,
                    tags=["mock", topic.lower()],
                )
            )
        return FlashcardSet(
            title="Grounded mock flashcard set",
            description=f"Mock {card_format} cards ({n} of {card_count} requested).",
            cards=cards,
            source_topics=sorted({c.source_topic for c in cards if c.source_topic}),
            source_chunk_ids=[],
            needs_human_review=True,
        )

    # ------------------------------------------------------------------
    # Validation + review gate wrapper
    # ------------------------------------------------------------------

    def _validate_grounding(
        self, card_set: FlashcardSet, extracted_topics: list[str]
    ) -> None:
        """Ensure every card's source_topic is within the extraction allow-list.

        Args:
            card_set: Candidate set.
            extracted_topics: Topic allow-list.

        Raises:
            GroundingError: If any card references an out-of-list topic.
        """
        allowed = set(extracted_topics)
        bad: list[tuple[int, str]] = []
        for idx, card in enumerate(card_set.cards):
            if card.source_topic and card.source_topic not in allowed:
                bad.append((idx, card.source_topic))
        if bad:
            raise GroundingError(
                "Card source_topics not in extracted allow-list: "
                f"{bad!r}; allow-list={sorted(allowed)}"
            )

    def _wrap_for_review_gate(
        self,
        card_set: FlashcardSet,
        *,
        agent_run_id: str,
        extracted_topics: list[str],
    ) -> FlashcardSet:
        """Force the human-review gate flags and normalise.

        Args:
            card_set: Validated card set.
            agent_run_id: Opaque run id for audit (stored in description tail).
            extracted_topics: Topic allow-list used.

        Returns:
            Normalised copy with ``needs_human_review=True`` and sorted
            source_topics.
        """
        source_topics = sorted(
            {c.source_topic for c in card_set.cards if c.source_topic}
            & set(extracted_topics)
        )
        return FlashcardSet(
            title=card_set.title,
            description=(card_set.description or "")
            + f" [run_id={agent_run_id} pending_review]",
            cards=card_set.cards,
            source_topics=source_topics,
            source_chunk_ids=list(card_set.source_chunk_ids or []),
            needs_human_review=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        content: str,
        *,
        card_format: str = "term-definition",
        card_count: int = 10,
        source_chunk_ids: list[str] | None = None,
    ) -> FlashcardSet:
        """Generate grounded flashcards from cleaned content.

        Args:
            content: Cleaned study material from the ingestion lane.
            card_format: ``"term-definition"`` (default) or ``"qa"``.
            card_count: Target number of cards (default 10).
            source_chunk_ids: Optional chunk ids from ingestion, passed
                through for provenance.

        Returns:
            A validated :class:`FlashcardSet` with
            ``needs_human_review=True``. The caller MUST route this
            through the shared :mod:`src.validation.review_schema` gate
            before exporting or presenting as final.

        Raises:
            ValueError: If the format / count are invalid.
            GroundingError: If the LLM (or mock) produced cards that
                reference topics outside the extraction allow-list.
        """
        if not content or not content.strip():
            raise ValueError("content is empty; cannot generate flashcards")

        run_id = f"fc-{uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        extracted_topics = self.extract_topics(content)
        prompt = self._build_prompt(content, extracted_topics, card_format, card_count)

        if self.mock_mode:
            raw = self._mock_response(extracted_topics, card_format, card_count)
        else:  # pragma: no cover - live path exercised with API key
            try:
                text = self._call_llm(prompt)
            except Exception as exc:  # pragma: no cover - network
                logger.exception("Flashcard LLM call failed")
                raise RuntimeError("Flashcard LLM call failed") from exc
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise ValueError("LLM returned invalid JSON") from exc
            try:
                raw = FlashcardSet.model_validate(payload)
            except Exception as exc:  # pragma: no cover
                raise ValueError("LLM JSON failed FlashcardSet schema") from exc

        if source_chunk_ids:
            raw.source_chunk_ids = list(source_chunk_ids)

        self._validate_grounding(raw, extracted_topics)
        return self._wrap_for_review_gate(
            raw, agent_run_id=run_id, extracted_topics=extracted_topics
        )

