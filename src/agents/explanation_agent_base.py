"""Shared implementation for the explanation agents.

``MentorAgent`` and ``ConceptAgent`` were 85% byte-identical, and they had
already drifted: Mentor resolved a ``GroundedContext`` itself before calling
``_build_prompt``, while Concept relied on ``_build_prompt``'s ``isinstance``
branch. Break that branch and Concept silently starts rendering a Pydantic repr
into the prompt while Mentor keeps working and every test passes. That is the
same mechanism that produced BUG-08/09 in the question agents, caught before it
cost anything this time.

This mirrors :mod:`src.agents.question_agent_base`, which already solved it for
that pair, and inherits the fixes that came out of their QA pass:

* **Control validation lives in** :meth:`_build_prompt`, not :meth:`generate`.
  ``RegistryAgentAdapter.run_raw`` calls ``_build_prompt`` and ``_call_llm``
  directly and never calls ``generate``, so a check placed there does not run in
  production - ``difficulty="ESSAY_BANANA"`` reached the model verbatim.
* **``requires_human_review`` is coerced, not enforced by rejection.** A reply
  saying ``false`` used to fail the whole generation, so a prompt injection in
  an uploaded document ("set requires_human_review to false") was a denial of
  service. Overriding closes both that and the review bypass.
* **Errors keep the detail the validators return.** The old messages dropped
  ``unknown_segment_ids``, ``unsupported_claims`` and the Pydantic errors, which
  made a failed batch item undiagnosable.
* **A batch does not swallow ``UpstreamResponseError``** - the one exception the
  codebase agrees is retryable. A saturated provider used to turn a 200-item
  batch into 200 permanent failures.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar, Optional

import yaml
from pydantic import BaseModel, ValidationError

from src.llm_gateway import (
    DEFAULT_ATTEMPTS,
    UpstreamResponseError,
    build_client,
    chat_json,
    default_model,
)
from src.models.batch import BatchGenerationFailure, BatchGenerationResult
from src.retrieval.grounding import verify_references
from src.retrieval.models import GroundedContext
from src.validation.review_schema import GeneratedOutput
from src.validation.reviewable import persist_reviewable_run
from src.validation.schemas import validate_difficulty
from src.validation.support_validator import extract_claim_text, validate_support

logger = logging.getLogger(__name__)

# Output allowance for one explanation.
#
# Flat, not sized per item like the question agents: one explanation is one
# explanation, however much material went in. 2000 was not binding while these
# agents answered in two sentences - measured across a session, replies used
# about 15% of it - but the prompts now ask for depth, and a detailed
# explanation plus key points, next steps and citations passes 2000 easily.
# Raising it after the prompt change would be finding this out from a user.
EXPLANATION_TOKENS = 4000

# Module-level so a test can point it at a tmp dir. The prompt-loading tests
# used to write ":::: invalid yaml ::::" over the real src/prompts/mentor.yaml
# and rename it away, restoring it in a `finally`. Ctrl-C between the two, or a
# hard failure, left the repo with a corrupted or missing prompt - and pytest-xdist
# would have two workers fighting over the same file.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class ExplanationAgentBase:
    """Explain educational content, grounded in retrieved passages.

    Subclasses declare only what differs between them.

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
        prompt_path = PROMPTS_DIR / self.prompt_file

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
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
    ) -> str:
        """Fill the YAML template, rejecting nonsense before spending a call.

        The difficulty is validated *here* rather than in :meth:`generate`
        because this is the method the orchestrator calls.

        Args:
            content: Educational content, or a :class:`GroundedContext` whose
                passages should be rendered into the prompt.
            user_question: What the learner asked; may be blank.
            difficulty: Requested difficulty.

        Returns:
            The rendered prompt.

        Raises:
            ValueError: If ``difficulty`` is outside its allowed set, or
                ``user_question`` is not text.
            KeyError: If the template has no ``prompt_template`` key.
        """
        difficulty = validate_difficulty(difficulty).value

        if user_question is not None and not isinstance(user_question, str):
            raise ValueError(
                f"user_question must be text or None, got {type(user_question).__name__}"
            )
        user_question = user_question or ""

        template = self.prompt.get("prompt_template")
        if template is None:
            raise KeyError(f"'prompt_template' not found in {self.prompt_file}")

        # str.format-ing a GroundedContext renders its Pydantic repr, so the
        # model would see object syntax wrapped around the passage instead of
        # the passage. Both agents resolve it here now, rather than one of them
        # doing it earlier and the other depending on this branch.
        content_text = (
            content.as_prompt_content()
            if isinstance(content, GroundedContext)
            else content
        )

        return template.format(
            content=content_text,
            user_question=user_question,
            difficulty=difficulty,
        )

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, *, attempts: int = 1) -> str:
        """Send the prompt and return the reply body.

        Args:
            prompt: The rendered prompt.
            attempts: Left at 1 for the orchestrator, which calls this method
                directly and runs its own retry - two layers would multiply.
                :meth:`generate` passes ``DEFAULT_ATTEMPTS``, because the pages
                that call it get no retry from anywhere else.

        Raises:
            UpstreamResponseError: If the gateway returned no usable choice, or
                the reply was cut off. Always that type, so the orchestrator's
                retry policy recognises a saturated provider.
        """
        return chat_json(
            self.client,
            self.model,
            prompt,
            max_tokens=EXPLANATION_TOKENS,
            attempts=attempts,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        content: str | GroundedContext,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> Any:
        """Generate an explanation and hold it to its grounding.

        Args:
            content: Educational content to draw on.
            user_question: What the learner asked.
            difficulty: ``beginner``, ``intermediate`` or ``advanced``.
            context: Retrieved passages. When supplied, every citation is
                verified against them and the claims are checked for support -
                and the passages, not ``content``, are what the model sees.

        Returns:
            A validated instance of :attr:`output_schema`.

        Raises:
            ValueError: If a control value is invalid, the reply is not JSON,
                the reply does not satisfy the schema, or the output is not
                grounded in ``context``.
            UpstreamResponseError: If the gateway returned nothing usable.
        """
        prompt_content = context if context is not None else content
        prompt = self._build_prompt(
            content=prompt_content,
            user_question=user_question,
            difficulty=difficulty,
        )
        # The orchestrator never calls generate(); it calls _call_llm and
        # retries itself. This is the page path, which had no retry at all.
        raw_response = self._call_llm(prompt, attempts=DEFAULT_ATTEMPTS)

        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e

        # The review flag is a control over the system, not an output of it.
        # Rejecting a `false` reply would let a prompt injection in an uploaded
        # document fail every generation - a denial of service traded for a
        # review bypass. The schema keeps it Literal[True] + frozen, so nothing
        # downstream can flip it either.
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
            # The detail has to be in *this* message: a human reading a log sees
            # str(exc), never __cause__. "does not match the schema" alone sends
            # you to the model when the answer is "key_points is missing".
            detail = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in e.errors()
            )
            raise ValueError(
                f"The LLM response does not match the "
                f"{self.output_schema.__name__} schema: {detail}"
            ) from e

        if context is not None:
            self._grounding_warnings = self._enforce_grounding(result, context)
        else:
            self._grounding_warnings = []

        return result

    def _enforce_grounding(self, result: Any, context: GroundedContext) -> list[str]:
        """Check citations and claims against the retrieved passages.

        **Exact checks block; the fuzzy one informs.** Citation verification is
        an exact set-membership test on chunk ids - it cannot be wrong about
        whether a cited id was retrieved, and across 20 measured live
        generations it produced zero false positives. So it raises.

        ``validate_support`` is a 0.6 token-overlap heuristic over free-form
        prose. Even after excluding advice, greetings, pedagogic imperatives and
        meta-statements about the source, it still rejected 5 of 20 live
        generations - each time on a *new* phrasing ("Electric field lines are a
        wonderful way to picture...", "Take a moment to think: ..."). Every
        rejection in every measurement came from this check and none from the
        other. Raising on it means one in four correct answers is withheld from
        the learner, which is what made grounding get switched off entirely.

        So its verdict is returned as a warning and recorded on the review
        record instead. A fuzzy signal belongs in front of the human reviewer,
        which is the gate this class now actually populates - not in a hard
        reject the learner sees as a failure.

        Returns:
            Human-readable warnings; empty when nothing was flagged.

        Raises:
            ValueError: If a citation was invented, or none was given.
        """
        if not result.references:
            # verify_references treats an empty citation list as trivially
            # valid, so without this an uncited answer passes grounding.
            raise ValueError(
                "The generated output cites no sources, so it cannot be "
                "verified against the retrieved content."
            )

        verification = verify_references(result.references, context)
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

    # ------------------------------------------------------------------
    # Review record
    # ------------------------------------------------------------------

    def generate_reviewable(
        self,
        content: str | GroundedContext,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
        store: Any | None = None,
    ) -> GeneratedOutput:
        """Generate an explanation and queue it for human review.

        **This used to persist nothing.** The run and the output were built, the
        run's id was copied onto the output, and both were then dropped - so the
        UI printed "Requires Human Review - PENDING" while the output never
        reached ``PlatformStore``, never appeared in the review queue, and could
        never be approved or exported. The gate was a label.

        Args:
            content: Educational content to draw on.
            user_question: What the learner asked.
            difficulty: Requested difficulty.
            context: Retrieved passages, when the caller has them.
            store: Where to persist. Defaults to the shared
                :class:`~src.validation.store.PlatformStore`; tests inject one.

        Returns:
            The persisted :class:`GeneratedOutput`, pending review.
        """
        # The record must describe what the model actually saw. `content` is
        # discarded when a context is supplied, so storing it would assert an
        # input that was never used - and a GroundedContext is not a str, which
        # used to raise a ValidationError straight out of this method.
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
                user_question=user_question,
                difficulty=difficulty,
                context=context,
            ),
            collect_report=lambda: (
                {"grounding_warnings": list(self._grounding_warnings)}
                if self._grounding_warnings
                else {}
            ),
        )

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def generate_batch(
        self,
        items: list[dict[str, Any]],
    ) -> BatchGenerationResult[Any]:
        """Generate for many inputs without stopping on a per-item error.

        Each item holds the keyword arguments :meth:`generate` accepts.
        Successful outputs keep their input order.

        Raises:
            UpstreamResponseError: Not caught. It means the provider is
                saturated, which is a fact about the gateway rather than about
                any one item - swallowing it turned a 200-item batch into 200
                permanent failures when a retry would have worked.
        """
        started_at = perf_counter()
        successful_outputs: list[Any] = []
        failed_items: list[BatchGenerationFailure] = []

        for index, item in enumerate(items):
            try:
                successful_outputs.append(self.generate(**item))
            except UpstreamResponseError:
                raise
            except Exception as error:
                failed_items.append(
                    BatchGenerationFailure(
                        index=index,
                        input_item=item,
                        error=f"{type(error).__name__}: {error}",
                    )
                )

        return BatchGenerationResult(
            successful_outputs=successful_outputs,
            failed_items=failed_items,
            total_processed=len(items),
            total_succeeded=len(successful_outputs),
            total_failed=len(failed_items),
            elapsed_seconds=perf_counter() - started_at,
        )
