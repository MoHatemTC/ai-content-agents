"""Flashcard agent: grounded term-definition / Q-A cards from content.

The flashcard agent is the learner-facing entry point for retrieval-practice
outputs. It follows the repository-wide four-step pattern:

1. :meth:`_extract_topics` pulls a strict allow-list of topics from the raw
   content using a deterministic keyword/token heuristic (no LLM trust at
   this step).
2. :meth:`_load_prompt` / :meth:`_build_prompt` fill the study-lane YAML
   template that *forces* the LLM to only use that allow-list.
3. :meth:`_call_llm` goes to LiteLLM through the shared client in
   :mod:`src.llm_gateway`. Tests inject a double; there is no mode flag.
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
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.validation.review_schema import GeneratedOutput
from src.validation.reviewable import persist_reviewable_run
from src.llm_gateway import build_client, default_model
from src.schemas import FlashcardSet
from src.study.llm_client import (
    UpstreamResponseError,
    call_llm,
    output_budget,
    parse_json,
    schema_block,
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
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "there",
        "here",
        "of",
        "in",
        "on",
        "at",
        "to",
        "from",
        "by",
        "for",
        "with",
        "without",
        "within",
        "into",
        "onto",
        "up",
        "out",
        "over",
        "under",
        "above",
        "below",
        "between",
        "among",
        "across",
        "through",
        "during",
        "before",
        "after",
        "while",
        "since",
        "until",
        "about",
        "against",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "done",
        "has",
        "have",
        "had",
        "having",
        "can",
        "could",
        "may",
        "might",
        "must",
        "shall",
        "should",
        "will",
        "would",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "their",
        "his",
        "her",
        "our",
        "your",
        "my",
        "we",
        "you",
        "us",
        "me",
        "him",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "every",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "too",
        "very",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "first",
        "second",
        "next",
        "last",
        "also",
        "just",
        "now",
        "new",
        "old",
        "way",
        "get",
        "let",
        "see",
        "make",
        "made",
        "use",
        "used",
        "using",
        "take",
        "taken",
        "give",
        "given",
        "call",
        "called",
        "note",
        "noted",
        "following",
        "right",
        "left",
        "top",
        "bottom",
        "thing",
        "things",
    ]
)

# How a book refers to itself. Kept apart from the stopwords because it is a
# different idea: these are perfectly good English words that happen to be
# publishing apparatus. In a 1,598-page physics textbook "Fig" appears 3,483
# times - the 13th most frequent token, ahead of "mass", "speed" and "charge" -
# so frequency ranking put the typesetting at the top of the syllabus.
_DOCUMENT_FURNITURE = frozenset(
    [
        "fig",
        "figs",
        "figure",
        "figures",
        "table",
        "tables",
        "chart",
        "charts",
        "diagram",
        "diagrams",
        "chapter",
        "chapters",
        "section",
        "sections",
        "subsection",
        "appendix",
        "appendices",
        "example",
        "examples",
        "exercise",
        "exercises",
        "problem",
        "problems",
        "question",
        "questions",
        "solution",
        "solutions",
        "answer",
        "answers",
        "summary",
        "review",
        "test",
        "quiz",
        "page",
        "pages",
        "part",
        "parts",
        "unit",
        "units",
        "lesson",
        "lessons",
        "equation",
        "equations",
        "eq",
        "formula",
        "formulas",
        "shown",
        "show",
        "see",
        "refer",
        "reference",
        "references",
        "note",
        "notes",
        "caption",
    ]
)

# The smallest number of times a two-word phrase must occur before it counts as
# a term rather than a coincidence of adjacent words.
_MIN_BIGRAM_COUNT = 2

# Multi-word terms are what real topics look like - "kinetic energy",
# "potential difference" - so they outrank single words of the same frequency.
_BIGRAM_WEIGHT = 4

# A whole-line "[chunk_id]" marker as GroundedContext.as_prompt_content writes
# them. Anchored per line so a bracketed aside inside a passage is left alone.
_CHUNK_MARKER = re.compile(r"^\s*\[[^\]\n]+\]\s*$", re.MULTILINE)


class GroundingError(ValueError):
    """Raised when a card references a topic not in the extraction allow-list."""


class FlashcardAgent:
    """Grounded flashcard generator.

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
        prompt_path = Path(__file__).resolve().parent / "prompts" / "flashcards.yaml"
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

        # Retrieved content arrives as "[chunk_id]\npassage" - the markers the
        # prompts ask the model to cite. The token pattern below reads
        # `heat-1-c0001` as the words `heat` and `c0001`, so a chunk id became
        # a "topic" and the model could be asked to build a flashcard about
        # c0001. Callers that pass their own allow-list avoid this entirely;
        # this is for the ones that do not.
        content = _CHUNK_MARKER.sub(" ", content)

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

    @staticmethod
    def canonical_topic(topic: str | None, allowed: list[str]) -> str | None:
        """Return ``topic``'s allow-list spelling, or ``None`` if it is not one.

        The allow-list keeps whichever casing the document uses most, so it
        carries ``conduction`` while a model writing a plan entry or a card
        front naturally capitalises it. Exact string equality then rejected
        genuinely grounded output: a live study plan failed with
        ``topics not in extraction allow-list: ['Conduction']`` while the list
        it was checked against contained ``conduction``.

        Matching case-insensitively and returning the *allow-list's* spelling
        keeps the property that makes the list safe - a topic is always quoted
        from the document, never invented - while not rejecting a model for
        capitalising a sentence.

        Args:
            topic: What the model produced.
            allowed: The allow-list.

        Returns:
            The canonical spelling, or ``None`` when the topic is not allowed.
        """
        if not topic:
            return None
        return {item.casefold(): item for item in allowed}.get(topic.casefold())

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

        template = self.prompt_cfg.get("prompt_template")
        if not template:
            raise KeyError("'prompt_template' missing in flashcards.yaml")

        rendered = template.format(
            content=content,
            extracted_topics=json.dumps(extracted_topics, ensure_ascii=False),
            card_format=card_format,
            card_count=card_count,
        )
        # The literal example in the YAML shows the shape; this appends the
        # generated JSON schema as well. Both exist for the same reason - the
        # YAML used to name `FlashcardSet` and never send it, so the model
        # guessed `{"cards": [...]}`, omitted the required `title`, and every
        # live call failed to validate. Belt and braces, deliberately.
        return f"{rendered}{schema_block(FlashcardSet)}"

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int | None = None) -> str:
        """Send the prompt to LiteLLM and return the raw text response.

        Args:
            prompt: Fully rendered prompt.

        Returns:
            Stripped LLM response body.

        Raises:
            UpstreamResponseError: If the gateway returned no usable choice.
        """
        return call_llm(self.client, self.model, prompt, max_tokens=max_tokens)

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
        bad: list[tuple[int, str]] = []
        for idx, card in enumerate(card_set.cards):
            if not card.source_topic:
                continue
            canonical = self.canonical_topic(card.source_topic, extracted_topics)
            if canonical is None:
                bad.append((idx, card.source_topic))
            else:
                # Rewrite to the allow-list's spelling so the card, and the
                # source_topics derived from it, quote the document exactly.
                card.source_topic = canonical
        if bad:
            raise GroundingError(
                "Card source_topics not in extracted allow-list: "
                f"{bad!r}; allow-list={sorted(extracted_topics)}"
            )

    def _wrap_for_review_gate(
        self,
        card_set: FlashcardSet,
        *,
        extracted_topics: list[str],
    ) -> FlashcardSet:
        """Force the human-review gate flags and normalise.

        The run id used to be appended to ``description`` as
        "[run_id=fc-... pending_review]", and app.py renders that field
        verbatim - so every learner read the audit trail off the front of the
        card set. It belongs on the persisted AgentRun, which is where
        :meth:`generate_reviewable` now puts it.

        Args:
            card_set: Validated card set.
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
            description=card_set.description,
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
        extracted_topics: list[str] | None = None,
    ) -> FlashcardSet:
        """Generate grounded flashcards from cleaned content.

        Args:
            content: Cleaned study material from the ingestion lane.
            card_format: ``"term-definition"`` (default) or ``"qa"``.
            card_count: Target number of cards (default 10).
            source_chunk_ids: Optional chunk ids from ingestion, passed
                through for provenance.
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
            A validated :class:`FlashcardSet` with
            ``needs_human_review=True``. The caller MUST route this
            through the shared :mod:`src.validation.review_schema` gate
            before exporting or presenting as final.

        Raises:
            ValueError: If the format / count are invalid.
            GroundingError: If the LLM produced cards that reference
                topics outside the extraction allow-list.
        """
        if not content or not content.strip():
            raise ValueError("content is empty; cannot generate flashcards")

        if extracted_topics is None:
            extracted_topics = self.extract_topics(content)
        prompt = self._build_prompt(content, extracted_topics, card_format, card_count)

        try:
            text = self._call_llm(prompt, output_budget(card_count))
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
        return self._wrap_for_review_gate(raw, extracted_topics=extracted_topics)

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
        "pending review" while the reviewer's queue stayed empty, so a flashcard set
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
            agent_name="flashcard_agent",
            output_type="flashcard_set",
            output_schema=FlashcardSet,
            model=self.model,
            input_context=content,
            source_chunk_ids=source_chunk_ids,
            generate=lambda: self.generate(
                content,
                source_chunk_ids=source_chunk_ids,
                **kwargs,
            ),
        )
