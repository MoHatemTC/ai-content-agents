"""
Concept Explanation Agent

This agent explains educational concepts using
uploaded educational content.
It loads its prompt template from YAML,
sends the prompt to the LLM,
and validates the response using the ConceptOutput schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from src.llm_gateway import build_client, default_model, response_text
from pydantic import ValidationError

from src.models.batch import BatchGenerationFailure, BatchGenerationResult
from src.retrieval.models import GroundedContext
from src.retrieval.grounding import verify_references
from src.validation.review_schema import AgentRun, GeneratedOutput
from src.validation.schemas import ConceptOutput, DifficultyLevel, validate_difficulty
from src.validation.support_validator import extract_claim_text, validate_support
from src.validation.validator_base import ValidatorBase, build_generated_output

load_dotenv()


class ConceptAgent:
    """
    AI Concept Explanation Agent.

    Responsibilities:
    - Load concept prompt template
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
        Load concept.yaml.

        Returns:
            Dictionary containing the YAML configuration.
        """

        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "prompts"
            / "concept.yaml"
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
                "Invalid YAML syntax in concept.yaml."
            ) from e

        if data is None:
            raise ValueError("concept.yaml is empty.")

        if not isinstance(data, dict):
            raise TypeError(
                "concept.yaml must contain a YAML dictionary."
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
            raise KeyError("'prompt_template' not found in concept.yaml")

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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.3,
        )

        # These guards were correct but raised RuntimeError, which is not in
        # Orchestrator.transient_errors - so a saturated provider was recorded
        # as a permanent failure and never retried. That is BUG-09 in a
        # different costume: the same defect the question agents had, unfiled
        # because nothing tested this path through the orchestrator.
        # response_text raises UpstreamResponseError, which is retried, and
        # keeps these four messages verbatim.
        return response_text(response)



    def generate(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str | DifficultyLevel = DifficultyLevel.BEGINNER,
        context: GroundedContext | None = None,
    ) -> ConceptOutput:
        """
        Generate a concept explanation.

        Args:
            content:
                Educational content.

            user_question:
                Optional learner question.

            difficulty:
                Difficulty level.

            context:
                Optional retrieved content used to ground the explanation.
                When supplied, generated references and the explanation are
                validated against this context.

        Returns:
            Validated ConceptOutput object.
        """

        difficulty = validate_difficulty(difficulty)
        prompt_content = context if context is not None else content
        prompt = self._build_prompt(
            content=prompt_content,
            user_question=user_question,
            difficulty=difficulty.value,
        )

        raw_response = self._call_llm(prompt)

        try:
            response_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e
        

        try:
            result = ConceptOutput.model_validate(response_json)

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match ConceptOutput schema."
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
        """Generate a concept explanation and prepare it for human review.

        The returned record is always pending review. This method delegates all
        generation, schema, grounding, and support checks to :meth:`generate`
        before applying the shared validation and review-record pipeline.
        """
        agent_run = AgentRun(
            agent_name="concept_agent",
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
            ConceptOutput,
        )

        return build_generated_output(
            agent_run_id=agent_run.id,
            output_type="concept_explanation",
            output_schema=ConceptOutput,
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
    ) -> BatchGenerationResult[ConceptOutput]:
        """Generate concept explanations for multiple inputs without stopping on errors.

        Each item must contain the keyword arguments accepted by :meth:`generate`,
        including required ``content`` and optional ``user_question``,
        ``difficulty``, and ``context`` values. Successful outputs retain their
        original input order.
        """
        started_at = perf_counter()
        successful_outputs: list[ConceptOutput] = []
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
