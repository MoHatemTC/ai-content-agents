"""
Question Bank Agent

This agent generates grounded educational assessment questions
from uploaded educational content.
It loads its prompt template from YAML, sends the prompt to the LLM,
and validates the structured response using the QuestionBankOutput schema.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from src.models.batch import BatchGenerationFailure, BatchGenerationResult
from src.retrieval.grounding import verify_references
from src.retrieval.models import GroundedContext
from src.validation.guardrails import DEFAULT_RULES
from src.validation.question_rules import QuestionItemQualityRule
from src.validation.review_schema import AgentRun, GeneratedOutput
from src.validation.schemas import (
    DifficultyLevel,
    QuestionBankOutput,
    QuestionType,
    validate_difficulty,
    validate_question_type,
)
from src.validation.support_validator import validate_support
from src.validation.validator_base import ValidatorBase, build_generated_output

from pydantic import ValidationError

load_dotenv()


class QuestionBankAgent:
    """
    AI Question Bank Agent.

    Responsibilities:
    - Load question bank prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using QuestionBankOutput
    """

    def __init__(self, mock_mode: Optional[bool] = None) -> None:
        """Initialize the Question Bank Agent."""

        # Configure mock mode first.
        if mock_mode is None:
            self.mock_mode = (
                os.getenv("MOCK_MODE", "true").lower() == "true"
            )
        else:
            self.mock_mode = mock_mode

        if os.getenv("DEBUG"):
            print("MOCK MODE:", self.mock_mode)

        # Load the YAML prompt configuration.
        self.prompt = self._load_prompt()

        if not self.mock_mode:
            api_key = os.getenv("LITELLM_API_KEY")
            base_url = os.getenv("LITELLM_BASE_URL")
            self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")

            if not api_key:
                raise ValueError("Missing LITELLM_API_KEY environment variable.")

            if not base_url:
                raise ValueError("Missing LITELLM_BASE_URL environment variable.")

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
        Load question_bank.yaml.

        Returns:
            Dictionary containing the YAML configuration.
        """

        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "prompts"
            / "question_bank.yaml"
        )

        # Check if the YAML file exists
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}"
            )

        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

        except yaml.YAMLError as e:
            raise ValueError(
                "Invalid YAML syntax in question_bank.yaml."
            ) from e

        # Check if the YAML file is empty
        if data is None:
            raise ValueError("question_bank.yaml is empty.")

        # Ensure the YAML content is a dictionary
        if not isinstance(data, dict):
            raise TypeError(
                "question_bank.yaml must contain a YAML dictionary."
            )

        return data
    

    def _build_prompt(
        self,
        content: str | GroundedContext,
        question_type: str,
        difficulty: str,
        num_questions: int,
    ) -> str:
        """
        Fill the YAML prompt template.

        Args:
            content:
                Educational content.

            question_type:
                Requested question type.

            difficulty:
                Difficulty level.

            num_questions:
                Number of questions to generate.

        Returns:
            Final prompt string.
        """

        template = self.prompt.get("prompt_template")

        if template is None:
            raise KeyError("'prompt_template' not found in question_bank.yaml")

        content_text = content.as_prompt_content() if isinstance(content, GroundedContext) else content
        return template.format(
            content=content_text,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
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

        if not response.choices:
            raise ValueError(
                "The LLM returned no choices."
            )

        message = response.choices[0].message

        if message is None:
            raise ValueError(
                "The LLM returned an empty message."
            )

        content = message.content

        # Some providers return reasoning only
        # and leave content empty
        if not content:
            raise ValueError(
                "The LLM returned no content. "
                f"Finish reason: {response.choices[0].finish_reason}"
            )

        return content.strip()


    def generate(
        self,
        content: str,
        question_type: str = "mcq",
        difficulty: str | DifficultyLevel = DifficultyLevel.BEGINNER,
        num_questions: int = 1,
        context: GroundedContext | None = None,
        user_question: str | None = None,
    ) -> QuestionBankOutput:
        """
        Generate grounded educational questions.

        Args:
            content:
                Educational content.

            question_type:
                Requested question type.

            difficulty:
                Difficulty level.

            num_questions:
                Number of questions to generate.

        Returns:
            Validated QuestionBankOutput object.
        """

        question_type = validate_question_type(question_type)
        difficulty = validate_difficulty(difficulty)
        prompt = self._build_prompt(
            content=context if context is not None else content,
            question_type=question_type.value,
            difficulty=difficulty.value,
            num_questions=num_questions,
        )
        
        # Temporary mocked response used while LiteLLM is unavailable.
        MOCK_RESPONSE = """
        {
        "questions": [
            {
                "question": "Which loop repeats while a condition is true?",
                "options": [
                    "for",
                    "while",
                    "if",
                    "switch"
                ],
                "correct_answer": "while",
                "rationale": "A while loop repeats while its condition evaluates to true.",
                "difficulty": "beginner",
                "type": "mcq",
                "references": [
                    {
                        "segment_id": "chunk_001",
                        "text": "Python provides two loop types: for and while."
                    }
                ]
            }
        ],
        "requires_human_review": true
        }
        """

        if self.mock_mode:
            reference = (
                context.to_content_references()[0].model_dump()
                if context is not None
                else {
                    "segment_id": "chunk_001",
                    "text": "Python provides two loop types: for and while.",
                }
            )
            if question_type.value == "short_answer":
                options = None
                answer = "for and while"
                stem = "Which two loop types does Python provide?"
            elif question_type.value == "true_false":
                options = ["True", "False"]
                answer = "True"
                stem = "True or False: Python provides for and while loops."
            else:
                options = ["for", "while", "if", "switch"]
                answer = "while"
                stem = "Which loop repeats while a condition is true?"
            questions = [
                {
                    "question": stem if index == 0 else f"{stem} ({index + 1})",
                    "options": options,
                    "correct_answer": answer,
                    "rationale": reference["text"],
                    "difficulty": difficulty.value,
                    "type": question_type.value,
                    "references": [reference],
                }
                for index in range(num_questions)
            ]
            raw_response = json.dumps(
                {"questions": questions, "requires_human_review": True}
            )
        else:
            raw_response = self._call_llm(prompt)


        # print("\n=== RAW LLM RESPONSE ===")
        # print(raw_response) # to debug/check the raw response from the LLM
        # print("========================\n")

        try:
            response_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e
        

        try:
            result = QuestionBankOutput.model_validate(response_json)

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match QuestionBankOutput schema."
            ) from e

        if context is not None:
            for question in result.questions or []:
                verification = verify_references(question.references, context)
                if not verification.valid:
                    raise ValueError(
                        "The generated references are not grounded in the retrieved content."
                    )
                cited_ids = {
                    reference.segment_id
                    for reference in (question.references or [])
                    if reference is not None and getattr(reference, "segment_id", None) is not None
                }
                cited_context = context.model_copy(
                    update={
                        "chunks": [
                            chunk for chunk in context.chunks
                            if chunk.chunk.chunk_id in cited_ids
                        ]
                    }
                )
                claims = [q for q in [question.rationale] if q]
                if question.type is not QuestionType.TRUE_FALSE and question.correct_answer:
                    claims.insert(0, question.correct_answer)
                support = validate_support(claims, cited_context)
                if not support.supported:
                    raise ValueError(
                        "The generated answer key or rationale contains unsupported claims."
                    )

        return result

    def generate_reviewable(
        self,
        content: str,
        question_type: str = "mcq",
        difficulty: str = "beginner",
        num_questions: int = 1,
        context: GroundedContext | None = None,
    ) -> GeneratedOutput:
        """Generate Question Bank content as a pending human-review record."""
        agent_run = AgentRun(
            agent_name="question_bank_agent",
            input_context=context.as_prompt_content() if context is not None else content,
            source_chunk_ids=context.chunk_ids if context is not None else [],
            model=self.model,
        )
        generated = self.generate(
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
            context=context,
        )
        payload = generated.model_dump()
        result, validated = ValidatorBase().validate(
            payload,
            QuestionBankOutput,
            rules=[*DEFAULT_RULES, QuestionItemQualityRule()],
        )
        return build_generated_output(
            agent_run_id=agent_run.id,
            output_type="question_bank",
            output_schema=QuestionBankOutput,
            payload=validated.model_dump() if validated is not None else payload,
            result=result,
        )

    def generate_batch(
        self, items: list[dict[str, Any]]
    ) -> BatchGenerationResult[QuestionBankOutput]:
        """Generate question banks sequentially while retaining item failures."""
        started_at = perf_counter()
        successful_outputs: list[QuestionBankOutput] = []
        failed_items: list[BatchGenerationFailure] = []
        for index, item in enumerate(items):
            try:
                successful_outputs.append(self.generate(**item))
            except Exception as error:
                failed_items.append(
                    BatchGenerationFailure(index=index, input_item=item, error=str(error))
                )
        return BatchGenerationResult(
            successful_outputs=successful_outputs,
            failed_items=failed_items,
            total_processed=len(items),
            total_succeeded=len(successful_outputs),
            total_failed=len(failed_items),
            elapsed_seconds=perf_counter() - started_at,
        )
