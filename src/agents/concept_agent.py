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
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
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

    def __init__(self, mock_mode: Optional[bool] = None) -> None:
        """Initialize the Concept Agent."""

        if mock_mode is None:
            self.mock_mode = (
                os.getenv("MOCK_MODE", "true").lower() == "true"
            )
        else:
            self.mock_mode = mock_mode

        self.prompt = self._load_prompt()

        if not self.mock_mode:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    "openai is required when MOCK_MODE=false. Install it or enable mock mode."
                ) from e

            api_key = os.getenv("LITELLM_API_KEY")
            base_url = os.getenv("LITELLM_BASE_URL")
            self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")

            if not api_key:
                raise ValueError(
                    "Missing LITELLM_API_KEY environment variable."
                )

            if not base_url:
                raise ValueError(
                    "Missing LITELLM_BASE_URL environment variable."
                )

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,
            )
        else:
            self.client = None
            self.model = None
    

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

        if self.client is None:
            raise RuntimeError(
                "LLM client is not initialized because mock mode is enabled."
            )

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

        if response is None:
            raise RuntimeError("LLM returned no response.")
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("LLM returned no choices.")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise RuntimeError("LLM returned an empty message.")
        content = getattr(message, "content", None)

        if not content:
            raise RuntimeError("LLM returned an empty response.")

        return content.strip()



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

        if self.mock_mode:
            chunk_id = (
                context.chunk_ids[0]
                if context is not None and context.chunk_ids
                else "chunk_001"
            )
            chunk_text = (
                context.chunks[0].chunk.text
                if context is not None and context.chunks
                else "Relevant content excerpt."
            )
            if context is not None:
                definition = chunk_text.strip()
                explanation = chunk_text.strip()
                key_points = ["for loops", "while loops"]
            elif difficulty is DifficultyLevel.BEGINNER:
                definition = "A loop repeats instructions."
                explanation = "Python has for and while loops."
                key_points = ["loops repeat instructions", "for loops", "while loops"]
            elif difficulty is DifficultyLevel.INTERMEDIATE:
                definition = "A loop repeats a block of code according to a rule."
                explanation = "Python has for and while loops."
                key_points = ["for loops iterate over iterables", "while loops are condition-based"]
            else:
                definition = (
                    "A loop is a control-flow construct that repeats a block based on iteration "
                    "over an iterable or evaluation of a condition."
                )
                explanation = (
                    "Python typically uses for loops for iteration over iterables and while loops "
                    "for condition-driven repetition. The choice depends on whether you are iterating "
                    "over a known collection or continuing until a stopping condition is reached."
                )
                key_points = [
                    "for loops iterate over iterables",
                    "while loops repeat based on a condition",
                    "choose based on iteration vs condition control",
                ]
            raw_response = json.dumps(
                {
                    "definition": definition,
                    "explanation": explanation,
                    "key_points": key_points,
                    "references": [
                        {
                            "segment_id": chunk_id,
                            "text": chunk_text[:240],
                        }
                    ],
                    "requires_human_review": True,
                }
            )
        else:
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
