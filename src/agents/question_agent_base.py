"""Shared implementation for the question-generating agents.

``QuestionBankAgent`` and ``TestHelpAgent`` were near-identical copies of each
other, differing only in a YAML filename and an output schema. That is what
produced BUG-08 and BUG-09 in the Sprint-4 QA report: the same eight lines were
written twice, one copy guarded an empty ``choices`` list and the other did not,
and the divergence went unnoticed because nobody diffs two files that are
supposed to be the same. One copy of the logic makes that class of defect
structurally impossible rather than merely unlikely.

**Where a fix goes matters more than it looks.** ``RegistryAgentAdapter.run_raw``
(``src/validation/orchestrator.py``) calls :meth:`_build_prompt` and
:meth:`_call_llm` directly and never calls :meth:`generate`, and it is the only
production path. So:

* validation that belongs to the *output* lives in the schema, and applies
  everywhere, because the orchestrator validates through it;
* validation that belongs to the *input* lives in :meth:`_build_prompt`;
* checks that need the *request* - the count, type and difficulty actually asked
  for - can only live in :meth:`generate`, because nothing else has them. That
  gap is real and is recorded in the QA report rather than papered over.

:meth:`_build_prompt` is also deliberately outside the adapter's ``try``, so an
input-validation error raised there cannot be mistaken for an upstream failure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, ValidationError

from src.llm_gateway import (
    DEFAULT_ATTEMPTS,
    build_client,
    chat_json,
    default_model,
)
from src.retrieval.grounding import verify_references
from src.retrieval.models import GroundedContext
from src.validation.review_schema import GeneratedOutput
from src.validation.reviewable import persist_reviewable_run
from src.validation.schemas import (
    validate_difficulty,
    validate_question_type,
)
from src.study.llm_client import max_tokens_default, output_budget
from src.validation.support_validator import extract_claim_text, validate_support

logger = logging.getLogger(__name__)

# Output allowance per question, for output_budget().
#
# The study lane's PER_ITEM_TOKENS is 200, measured on flashcards - "20
# flashcards cost 3,059 completion tokens, ~153 each". A flashcard is a front
# and a back. A QuestionItem is a stem, four options, a correct_answer, a
# rationale, and a references[].text quoting a retrieved passage, and that
# quote's size follows the chunk size. Measured against a real textbook
# (chunks averaging 766 chars): 369 tokens per item uncapped, ~253 once the
# prompt bounds the excerpt. 400 leaves headroom for an advanced question
# against a long chunk.
#
# Reusing the flashcard figure is what made five questions ask for 2000 tokens
# and come back truncated mid-JSON.
QUESTION_ITEM_TOKENS = 400


class QuestionCountError(ValueError):
    """The reply carried the wrong number of questions.

    Its own type so :meth:`QuestionAgentBase.generate` can retry this and only
    this. A model that under-delivers on a large request usually complies on a
    second attempt; a model that invents a citation invents it again, and a
    reply that fails the schema fails it the same way. Retrying those would
    spend a second call to print the same error.

    Subclasses ValueError, which is what callers already catch.
    """


class QuestionAgentBase:
    """Generate grounded assessment questions from educational content.

    Subclasses declare only what actually differs between them.

    Attributes:
        prompt_file: YAML template filename under ``src/prompts/``.
        output_schema: The Pydantic model the reply must conform to.
        agent_name: Name recorded on the :class:`AgentRun`.
        output_type: Label recorded on the :class:`GeneratedOutput`.
    """

    prompt_file: ClassVar[str]
    output_schema: ClassVar[type[BaseModel]]
    agent_name: ClassVar[str]
    output_type: ClassVar[str]

    def __init__(self, *, client: Any | None = None, model: str | None = None) -> None:
        """Create the agent.

        Args:
            client: An OpenAI-compatible client. Defaults to one built from the
                configured gateway; tests inject a double.
            model: Model id. Defaults to :func:`~src.llm_gateway.default_model`.
        """
        self.prompt = self._load_prompt()
        self.client = client if client is not None else build_client()
        self.model = model or default_model()
        # Warnings from the most recent generate(), read by generate_reviewable
        # so a fuzzy grounding signal reaches the reviewer rather than the
        # learner. See _enforce_grounding for why it is not a hard reject.
        self._grounding_warnings: list[str] = []

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def _load_prompt(self) -> dict[str, Any]:
        """Load the agent's YAML template.

        Raises:
            FileNotFoundError: If the template is missing.
            ValueError: If it is empty or not valid YAML.
            TypeError: If it does not contain a mapping.
        """
        prompt_path = (
            Path(__file__).resolve().parent.parent / "prompts" / self.prompt_file
        )

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax in {self.prompt_file}.") from e

        if data is None:
            raise ValueError(f"{self.prompt_file} is empty.")

        if not isinstance(data, dict):
            raise TypeError(f"{self.prompt_file} must contain a YAML dictionary.")

        return data

    def _build_prompt(
        self,
        content: str | GroundedContext,
        question_type: str,
        difficulty: str,
        num_questions: int,
    ) -> str:
        """Fill the YAML template, rejecting nonsense before spending a call.

        The control values are validated here rather than in :meth:`generate`
        because this method is on the production path and ``generate`` is not.

        Args:
            content: Educational content, or a :class:`GroundedContext` whose
                passages should be rendered into the prompt.
            question_type: Requested question type.
            difficulty: Requested difficulty.
            num_questions: How many questions to ask for.

        Returns:
            The rendered prompt.

        Raises:
            ValueError: If any control value is outside its allowed set, or
                ``num_questions`` is not a positive integer.
            KeyError: If the template has no ``prompt_template`` key.
        """
        question_type = validate_question_type(question_type).value
        difficulty = validate_difficulty(difficulty).value

        # bool is an int subclass, and True would otherwise render as "1".
        if isinstance(num_questions, bool) or not isinstance(num_questions, int):
            raise ValueError(
                f"num_questions must be an integer, got {num_questions!r}"
            )
        if num_questions < 1:
            raise ValueError(
                f"num_questions must be at least 1, got {num_questions}"
            )

        template = self.prompt.get("prompt_template")
        if template is None:
            raise KeyError(f"'prompt_template' not found in {self.prompt_file}")

        # A GroundedContext str.format-ed directly renders as a Pydantic repr -
        # `query='...' scope=RetrievalScope(...)` - so the model sees object
        # syntax wrapped around the passage instead of the passage (BUG-15).
        #
        # The orchestrator never reaches this branch: it calls
        # as_prompt_content() itself and hands run_raw a plain str. The branch
        # is for every other caller, for whom passing the context is the
        # natural thing to try.
        if isinstance(content, GroundedContext):
            content = content.as_prompt_content()

        return template.format(
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
        )

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(
        self, prompt: str, num_questions: int | None = None, *, attempts: int = 1
    ) -> str:
        """Send the prompt and return the reply body.

        Args:
            prompt: The rendered prompt.
            num_questions: Sizes the output budget when known.
            attempts: Left at 1 for the orchestrator, which calls this method
                directly and runs its own retry - two layers would multiply.
                :meth:`generate` passes ``DEFAULT_ATTEMPTS``, because the pages
                that call it get no retry from anywhere else.

        Raises:
            UpstreamResponseError: If the gateway returned no usable choice,
                or the reply was cut off by the output limit. Always that type,
                so the orchestrator's retry policy recognises a saturated
                provider without a per-agent convention (BUG-09).
        """
        return chat_json(
            self.client,
            self.model,
            prompt,
            attempts=attempts,
            # Sized to the request, like the study lane: the gateway refuses on
            # the *requested* ceiling, so a flat cap is wrong in both
            # directions. per_item is passed because the study lane's default
            # is calibrated for flashcards, which carry no citation.
            max_tokens=output_budget(num_questions, per_item=QUESTION_ITEM_TOKENS)
            if num_questions is not None
            else max_tokens_default(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        content: str | GroundedContext,
        question_type: str,
        difficulty: str,
        num_questions: int,
        context: GroundedContext | None = None,
    ) -> Any:
        """Generate questions and hold them to what was requested.

        Args:
            content: Educational content to draw on.
            question_type: ``mcq``, ``true_false`` or ``short_answer``.
            difficulty: ``beginner``, ``intermediate`` or ``advanced``.
            num_questions: Exactly how many questions to return.
            context: Retrieved passages. When supplied, every citation is
                verified against them and the rationales are checked for
                support, as mentor and concept already do.

        Returns:
            A validated instance of :attr:`output_schema`.

        A reply carrying the wrong *number* of questions is retried once.
        Models under-deliver on large requests - asking for 20 and getting 19
        is common - and discarding 19 good questions to print an error is a
        poor trade when a second attempt usually complies. The contract itself
        is unchanged: you never receive a count you did not ask for (BUG-01).

        Only the count is retried. A grounding failure means the model invented
        a citation, which it will invent again, and a schema failure fails the
        same way twice; both would spend a call to reprint the same message.

        The retry lives here rather than in :meth:`_call_llm` because the
        orchestrator calls that method directly and runs its own retry - and
        two layers multiply. It does compose with the transient retry inside
        ``chat_json``, so a request that is both short *and* hitting a
        saturated provider costs at most four calls. A retried 20-question
        generation is another ~8,400 output tokens, which is the price of not
        throwing away a nearly-complete set.

        Raises:
            ValueError: If a control value is invalid, the reply is not JSON,
                the reply does not satisfy the schema, or the citations are not
                grounded.
            QuestionCountError: If the count is still wrong after the retry.
            UpstreamResponseError: If the gateway returned nothing usable.
        """
        try:
            return self._generate_once(
                content, question_type, difficulty, num_questions, context
            )
        except QuestionCountError as first:
            logger.info(
                "%s returned the wrong question count (%s); retrying once.",
                self.output_schema.__name__,
                first,
            )

        return self._generate_once(
            content, question_type, difficulty, num_questions, context
        )

    def _generate_once(
        self,
        content: str | GroundedContext,
        question_type: str,
        difficulty: str,
        num_questions: int,
        context: GroundedContext | None = None,
    ) -> Any:
        """One generation attempt: prompt, call, parse, validate, enforce."""
        prompt = self._build_prompt(content, question_type, difficulty, num_questions)
        # The orchestrator never calls generate(); it calls _call_llm and
        # retries itself. This is the page path, which had no retry at all.
        raw_response = self._call_llm(
            prompt, num_questions, attempts=DEFAULT_ATTEMPTS
        )

        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e

        # The review flag is a control over the system, not an output of it.
        # Rejecting a `false` reply instead would let a prompt injection in an
        # uploaded document ("set requires_human_review to false") fail every
        # generation - trading a review bypass for a denial of service.
        # Overriding closes both here. On the orchestrator path generate() is
        # never called, so a `false` reply instead fails schema validation -
        # which is also safe: the run is recorded with the model's text intact
        # in payload["raw_output"] and surfaced to a reviewer, not silently
        # accepted. The schema keeps it Literal[True] + frozen either way, so
        # nothing downstream can flip it.
        if isinstance(payload, dict) and payload.get("requires_human_review") is not True:
            logger.warning(
                "%s returned requires_human_review=%r; forcing True. This can "
                "indicate a prompt injection in the source document.",
                self.output_schema.__name__,
                payload.get("requires_human_review"),
            )
            payload["requires_human_review"] = True

        try:
            result = self.output_schema.model_validate(payload)
        except ValidationError as e:
            # The detail has to be in *this* message: pytest.raises(match=...)
            # and a human reading a log both see str(exc), never __cause__.
            # A bare "does not match the schema" sends you to the model when
            # the real answer is "correct_answer is not one of the options".
            detail = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in e.errors()
            )
            raise ValueError(
                f"The LLM response does not match the "
                f"{self.output_schema.__name__} schema: {detail}"
            ) from e

        self._enforce_request(result, question_type, difficulty, num_questions)

        if context is not None:
            self._grounding_warnings = self._enforce_grounding(result, context)
        else:
            self._grounding_warnings = []

        return result

    # ------------------------------------------------------------------
    # Conformance
    # ------------------------------------------------------------------

    def _enforce_request(
        self,
        result: Any,
        question_type: str,
        difficulty: str,
        num_questions: int,
    ) -> None:
        """Hold the reply to the controls the caller asked for.

        The prompt says "Generate exactly N questions"; without this the count
        is a suggestion, and asking for 1 could return 3 (BUG-01). Type and
        difficulty are checked for the same reason.

        Raises:
            ValueError: If the reply does not match the request.
        """
        question_type = validate_question_type(question_type).value
        difficulty = validate_difficulty(difficulty).value

        actual = len(result.questions)
        if actual != num_questions:
            raise QuestionCountError(
                f"The model returned {actual} questions but exactly "
                f"{num_questions} were requested."
            )

        wrong_type = [
            index
            for index, item in enumerate(result.questions, start=1)
            if item.type.value != question_type
        ]
        if wrong_type:
            raise ValueError(
                f"Questions {wrong_type} are not of the requested type "
                f"{question_type!r}."
            )

        wrong_difficulty = [
            index
            for index, item in enumerate(result.questions, start=1)
            if item.difficulty.value != difficulty
        ]
        if wrong_difficulty:
            raise ValueError(
                f"Questions {wrong_difficulty} are not of the requested "
                f"difficulty {difficulty!r}."
            )

    # ------------------------------------------------------------------
    # Review record
    # ------------------------------------------------------------------

    def generate_reviewable(
        self,
        content: str | GroundedContext,
        question_type: str,
        difficulty: str,
        num_questions: int,
        context: GroundedContext | None = None,
        store: Any | None = None,
    ) -> GeneratedOutput:
        """Generate questions and queue them for human review.

        Mentor and concept gained this in #39, the study agents in #40; these
        two never had it, because nothing called them - they had no UI at all.
        Giving them a page without a gate would have re-introduced exactly the
        defect both of those fixed: a screen saying "pending review" over an
        output that reaches no queue and can therefore never be approved or
        exported.

        Args:
            content: Educational content, or the retrieved passages.
            question_type: ``mcq``, ``true_false`` or ``short_answer``.
            difficulty: ``beginner``, ``intermediate`` or ``advanced``.
            num_questions: Exactly how many questions to return.
            context: Retrieved passages. When supplied, citations are verified
                and rationales checked for support.
            store: Where to persist. Defaults to the shared
                :class:`~src.validation.store.PlatformStore`; tests inject one.

        Returns:
            The persisted :class:`GeneratedOutput`, pending review.
        """
        # The record has to describe what the model actually saw, and a
        # GroundedContext is not a str - storing the object would both fail
        # validation and assert an input nobody sent.
        resolved = (
            context.as_prompt_content()
            if context is not None
            else (
                content.as_prompt_content()
                if isinstance(content, GroundedContext)
                else content
            )
        )

        return persist_reviewable_run(
            store=store,
            agent_name=self.agent_name,
            output_type=self.output_type,
            output_schema=self.output_schema,
            model=self.model,
            input_context=resolved,
            source_chunk_ids=context.chunk_ids if context is not None else [],
            generate=lambda: self.generate(
                content=content,
                question_type=question_type,
                difficulty=difficulty,
                num_questions=num_questions,
                context=context,
            ),
            # A fuzzy signal belongs in front of the human reviewer, not in a
            # hard reject the learner reads as a failure. persist_reviewable_run
            # merges this into validation_report; the page renders it.
            collect_report=lambda: (
                {"grounding_warnings": list(self._grounding_warnings)}
                if self._grounding_warnings
                else {}
            ),
        )

    def _enforce_grounding(self, result: Any, context: GroundedContext) -> list[str]:
        """Check citations and rationales against the retrieved passages.

        These agents cite per question rather than at the top level, so the
        references are flattened before verification.

        **Exact checks block; the fuzzy one informs** - the same split
        :class:`~src.agents.explanation_agent_base.ExplanationAgentBase` made,
        for the same measured reason. Citation verification is set membership
        over chunk ids and produced zero false positives across 20 live
        generations, so it raises. ``validate_support`` is a 0.6 token-overlap
        heuristic over prose, and it rejected 5 of those same 20 - one correct
        answer in four withheld from the learner, which is what got grounding
        switched off wholesale last time.

        These two agents kept raising on both long after mentor and concept
        stopped, because nothing called them with a context: they had no UI
        until the Question Bank and Test Help pages existed. The moment they
        got one, they inherited the failure that fix was written to prevent.

        Returns:
            Human-readable warnings; empty when nothing was flagged.

        Raises:
            ValueError: If a citation was invented, or none was given.
        """
        references = [
            reference for item in result.questions for reference in item.references
        ]
        if not references:
            # verify_references treats an empty citation list as trivially
            # valid, so without this a question set that cites nothing at all
            # passes grounding. Every prompt here says "every question must
            # contain at least one grounding reference"; this is what makes
            # that true rather than merely requested.
            raise ValueError(
                "The generated questions cite no sources, so they cannot be "
                "verified against the retrieved content."
            )

        verification = verify_references(references, context)
        if not verification.valid:
            raise ValueError(
                "The generated references are not grounded in the retrieved "
                f"content: {verification.unknown_segment_ids}"
            )

        support = validate_support(extract_claim_text(result), context)
        if support.supported:
            return []

        logger.info(
            "%s: %d claim(s) not matched to the retrieved passages; flagged for "
            "review rather than rejected.",
            self.output_schema.__name__,
            len(support.unsupported_claims),
        )
        return [
            "Could not match this statement to the retrieved passages: "
            f"{claim}"
            for claim in support.unsupported_claims
        ]
