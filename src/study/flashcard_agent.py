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

from src.schemas import Flashcard, FlashcardSet
from src.study.llm_client import (
    UpstreamResponseError,
    call_llm,
    parse_json,
    schema_block,
    sentence_about,
)

load_dotenv()
logger = logging.getLogger(__name__)

# Topic extraction heuristic: deterministic, cheap, auditable, and never
# hallucinated - every topic is a literal substring of the content. The LLM is
# constrained to pick only from this list, so the list is the grounding
# contract, not a display detail: a junk entry is a junk card the guardrail
# will happily approve.
#
# Two vocabularies, because they answer different questions.

# Words that carry no subject matter. The previous list held ~50 entries and
# let "between", "each", "same", "which" and "use" through into the allow-list
# of a physics textbook.
_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those there here of in on
    at to from by for with without within into onto up out over under above
    below between among across through during before after while since until
    about against is are was were be been being am do does did done has have
    had having can could may might must shall should will would it its he she
    they them their his her our your my we you us me him what when where which
    who whom whose why how all any both each every few more most other some
    such no nor not only own same so too very one two three four five six seven
    eight nine ten first second next last also just now new old way get let see
    make made use used using take taken give given call called note noted
    following right left top bottom thing things
    """.split()
)

# How a book refers to itself. Kept apart from the stopwords because it is a
# different idea: these are perfectly good English words that happen to be
# publishing apparatus. In a 1,598-page physics textbook "Fig" appears 3,483
# times - the 13th most frequent token, ahead of "mass", "speed" and "charge" -
# so frequency ranking put the typesetting at the top of the syllabus.
_DOCUMENT_FURNITURE = frozenset(
    """
    fig figs figure figures table tables chart charts diagram diagrams
    chapter chapters section sections subsection appendix appendices
    example examples exercise exercises problem problems question questions
    solution solutions answer answers summary review test quiz
    page pages part parts unit units lesson lessons
    equation equations eq formula formulas
    shown show see refer reference references note notes caption
    """.split()
)

# The smallest number of times a two-word phrase must occur before it counts as
# a term rather than a coincidence of adjacent words.
_MIN_BIGRAM_COUNT = 2

# Multi-word terms are what real topics look like - "kinetic energy",
# "potential difference" - so they outrank single words of the same frequency.
_BIGRAM_WEIGHT = 4


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

        Every topic is a literal substring of ``content``, and the LLM may only
        pick from this list, so it is the grounding contract rather than a
        display detail.

        Ranking is by frequency, with two corrections. Function words and
        document furniture are dropped, because "Fig" is the 13th most common
        token in a physics textbook and frequency alone put the typesetting at
        the top of the syllabus. And repeated two-word phrases outrank single
        words, because real topics look like "kinetic energy" and "potential
        difference".

        The surface form is preserved: candidates are grouped case-insensitively
        but emitted in their most frequent original casing, so a topic stays a
        literal substring and hand-authored topics such as ``Gradient Descent``
        keep matching the allow-list by exact string equality.

        Args:
            content: Cleaned text from the ingestion lane.
            max_topics: Cap on allow-list size.

        Returns:
            Sorted, de-duplicated list of topic strings.
        """
        if not content or not content.strip():
            return []

        matches = list(re.finditer(r"\b[A-Za-z][A-Za-z0-9]{2,}\b", content))
        if not matches:
            return []

        words = [match.group() for match in matches]

        # Remember how each word is actually written so topics stay literal
        # substrings; "Energy" and "energy" are one candidate, emitted as
        # whichever spelling the document prefers.
        surface_forms: dict[str, Counter[str]] = {}
        for word in words:
            surface_forms.setdefault(word.lower(), Counter())[word] += 1

        def surface(key: str) -> str:
            return " ".join(
                surface_forms[part].most_common(1)[0][0]
                if part in surface_forms
                else part
                for part in key.split()
            )

        def is_content_word(word: str) -> bool:
            return word not in _STOPWORDS and word not in _DOCUMENT_FURNITURE

        lowered = [word.lower() for word in words]

        scores: Counter[str] = Counter()
        for word in lowered:
            if is_content_word(word):
                scores[word] += 1

        # Only pair words that are genuinely adjacent in the source. The token
        # regex skips anything under three characters, so pairing consecutive
        # *matches* would join words with something dropped between them:
        # "drawn around a positive charge" yielded "around positive", which
        # appears nowhere in the document and breaks the one property that
        # makes this list safe - that a topic is always quoted, never invented.
        bigrams: Counter[str] = Counter()
        for first, second in zip(matches, matches[1:]):
            gap = content[first.end() : second.start()]
            if gap and not gap.isspace():
                continue
            if is_content_word(first.group().lower()) and is_content_word(
                second.group().lower()
            ):
                bigrams[f"{first.group().lower()} {second.group().lower()}"] += 1

        for phrase, count in bigrams.items():
            if count >= _MIN_BIGRAM_COUNT:
                scores[phrase] = count * _BIGRAM_WEIGHT

        ranked = [topic for topic, _ in scores.most_common(max_topics)]
        return sorted({surface(topic) for topic in ranked})

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
            # The YAML's `output_schema: FlashcardSet` is a label, never sent to
            # the model. Without the actual shape it guessed `{"cards": [...]}`,
            # omitted the required `title`, and every live call failed to
            # validate.
            f"{schema_block(FlashcardSet)}"
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

        Raises:
            UpstreamResponseError: If the gateway returned no usable choice.
        """
        return call_llm(self.client, self.model, prompt)

    @staticmethod
    def _mock_response(
        extracted_topics: list[str],
        card_format: str,
        card_count: int,
        content: str = "",
    ) -> FlashcardSet:
        """Deterministic grounded sample for tests and local demoing.

        Args:
            extracted_topics: Topic allow-list.
            card_format: ``term-definition`` or ``qa``.
            card_count: Target count.
            content: The source text, so the cards can quote it instead of
                describing where to find it.

        Returns:
            Valid, grounded :class:`FlashcardSet` that passes every validator
            in :meth:`_validate_grounding`.
        """
        topics = extracted_topics or ["General topic"]
        n = min(card_count, max(1, len(topics)))
        cards: list[Flashcard] = []
        for i in range(n):
            topic = topics[i % len(topics)]
            # Quote the document rather than describing it. The previous text -
            # "X is a key concept described in the supplied content. See the
            # source text for a fuller treatment." - was the same sentence for
            # every card of every document, and it is what the app displayed,
            # since the UI hardcoded mock mode. A card that says where the
            # answer is instead of what it is teaches nothing.
            back = sentence_about(content, topic)
            front = topic if card_format == "term-definition" else f"What is {topic}?"
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
            raw = self._mock_response(
                extracted_topics, card_format, card_count, content
            )
        else:
            try:
                text = self._call_llm(prompt)
            except UpstreamResponseError:
                # Already says what the gateway did and whether it is worth
                # retrying; wrapping it in RuntimeError("call failed") would
                # replace a diagnosis with a shrug.
                logger.exception("Flashcard LLM call failed")
                raise
            raw = parse_json(text, FlashcardSet)

        if source_chunk_ids:
            raw.source_chunk_ids = list(source_chunk_ids)

        self._validate_grounding(raw, extracted_topics)
        return self._wrap_for_review_gate(
            raw, agent_run_id=run_id, extracted_topics=extracted_topics
        )
