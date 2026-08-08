"""
Mentor Agent

This agent provides supportive explanations for educational content.
It loads its prompt template from YAML, sends the prompt to the LLM,
and validates the structured response using the MentorOutput schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from src.llm_gateway import build_client, chat_json, default_model
from src.study.llm_client import max_tokens_default
from pydantic import ValidationError

from src.models.batch import BatchGenerationFailure, BatchGenerationResult
from src.retrieval.models import GroundedContext
from src.retrieval.grounding import verify_references
from src.validation.review_schema import AgentRun, GeneratedOutput
from src.validation.schemas import DifficultyLevel, MentorOutput, validate_difficulty
from src.validation.support_validator import extract_claim_text, validate_support
from src.validation.validator_base import ValidatorBase, build_generated_output

load_dotenv()


class MentorAgent:
    """
    AI Mentor Agent.

    Responsibilities:
    - Load mentor prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using Pydantic
    """


    def __init__(self, *, client: Any | None = None, model: str | None = None) -> None:
        self.prompt = self._load_prompt()
        self.client = client if client is not None else build_client()
        self.model = model or default_model()

    def _load_prompt(self) -> dict[str, Any]:
        """
        Load mentor.yaml.

        Returns:
            Dictionary containing the YAML configuration.
        """

        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "prompts"
            / "mentor.yaml"
        )

        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}"
            )

        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

        except yaml.YAMLError as e:
            raise ValueError(
                "Invalid YAML syntax in mentor.yaml."
            ) from e

        if data is None:
            raise ValueError("mentor.yaml is empty.")

        if not isinstance(data, dict):
            raise TypeError(
                "mentor.yaml must contain a YAML dictionary."
            )

        return data
    

    def _build_prompt(
        self,
        content: str | GroundedContext,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
    ) -> str:
        """
        Fill the YAML prompt template.

        Args:
            content:
                Educational content.

            user_question:
                Optional learner question.

            difficulty:
                Difficulty level.

        Returns:
            Final prompt string.
        """

        template = self.prompt.get("prompt_template")

        if template is None:
            raise KeyError("'prompt_template' not found in mentor.yaml")

        user_question = user_question or ""

        if isinstance(content, GroundedContext):
            content_text = content.as_prompt_content()
        else:
            content_text = content

        return template.format(
            content=content_text,
            user_question=user_question,
            difficulty=difficulty,
        )

    def _call_llm(self, prompt: str) -> str:
        """
        Send prompt to LiteLLM.

        Args:
            prompt:
                Final prompt.

        Returns:
            Raw LLM response.
        """


        # chat_json asks for JSON mode, because a physics explanation makes the
        # model write LaTeX and ec is not a valid JSON escape - a complete
        # reply that json.loads rejects. It also guards the response and reports
        # a truncated reply as such rather than as "invalid JSON".
        #
        # The guards behind it raise UpstreamResponseError rather than the
        # RuntimeError these agents used to raise: RuntimeError is not in
        # Orchestrator.transient_errors, so a saturated provider was recorded as
        # a permanent failure and never retried - BUG-09 in a different costume.
        return chat_json(
            self.client, self.model, prompt, max_tokens=max_tokens_default()
        )

    def generate(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str | DifficultyLevel = DifficultyLevel.BEGINNER,
        context: GroundedContext | None = None,
    ) -> MentorOutput:
        """
        Generate a mentoring response.

        Args:
            content:
                Educational content.

            user_question:
                Optional learner question.

            difficulty:
                Difficulty level.

        Returns:
            Validated MentorOutput object.
        """

        if context is not None:
            content_text = context.as_prompt_content()
        else:
            content_text = content

        difficulty = validate_difficulty(difficulty)
        prompt = self._build_prompt(
            content=content_text,
            user_question=user_question,
            difficulty=difficulty.value,
        )

        raw_response = self._call_llm(prompt)

        try:
            response_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e
        

        try:
            result = MentorOutput.model_validate(response_json)

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match MentorOutput schema."
            ) from e

        if context is not None:
            verification = verify_references(
                result.references,
                context,
            )

            if not verification.valid:
                raise ValueError(
                    "The generated references are not grounded in the retrieved content."
                )

        if context is not None:
            support = validate_support(extract_claim_text(result), context)

            if not support.supported:
                raise ValueError(
                    "The generated explanation contains unsupported claims."
                )


        return result

    def generate_reviewable(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate a mentoring response and prepare it for human review.

        The returned record is always pending review. This method delegates all
        generation, schema, grounding, and support checks to :meth:`generate`
        before applying the shared validation and review-record pipeline.
        """
        agent_run = AgentRun(
            agent_name="mentor_agent",
            input_context=content,
            source_chunk_ids=context.chunk_ids if context is not None else [],
            model=self.model,
        )
        generated = self.generate(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
            context=context,
        )
        payload = generated.model_dump()
        validator = ValidatorBase()
        validation_result, validated_output = validator.validate(
            payload,
            MentorOutput,
        )

        return build_generated_output(
            agent_run_id=agent_run.id,
            output_type="mentor_explanation",
            output_schema=MentorOutput,
            payload=(
                validated_output.model_dump()
                if validated_output is not None
                else payload
            ),
            result=validation_result,
        )

    def generate_batch(
        self,
        items: list[dict[str, Any]],
    ) -> BatchGenerationResult[MentorOutput]:
        """Generate mentor responses for multiple inputs without stopping on errors.

        Each item must contain the keyword arguments accepted by :meth:`generate`,
        including required ``content`` and optional ``user_question``,
        ``difficulty``, and ``context`` values. Successful outputs retain their
        original input order.
        """
        started_at = perf_counter()
        successful_outputs: list[MentorOutput] = []
        failed_items: list[BatchGenerationFailure] = []

        for index, item in enumerate(items):
            try:
                successful_outputs.append(self.generate(**item))
            except Exception as error:
                failed_items.append(
                    BatchGenerationFailure(
                        index=index,
                        input_item=item,
                        error=str(error),
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
