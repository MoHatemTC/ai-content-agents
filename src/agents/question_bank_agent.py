"""
Question Bank Agent

This agent generates grounded educational assessment questions
from uploaded educational content.
It loads its prompt template from YAML, sends the prompt to the LLM,
and validates the structured response using the QuestionBankOutput schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from src.llm_gateway import build_client, default_model
from src.validation.schemas import QuestionBankOutput, normalize_question_payload

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

    def __init__(self, *, client: Any | None = None, model: str | None = None) -> None:
        self.prompt = self._load_prompt()
        self.client = client if client is not None else build_client()
        self.model = model or default_model()

    def _load_prompt(self) -> dict[str, Any]:
        """
        Load question_bank.yaml.

        Returns:
            Dictionary containing the YAML configuration.
        """

        prompt_path = (
            Path(__file__).resolve().parent.parent / "prompts" / "question_bank.yaml"
        )

        # Check if the YAML file exists
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

        except yaml.YAMLError as e:
            raise ValueError("Invalid YAML syntax in question_bank.yaml.") from e

        # Check if the YAML file is empty
        if data is None:
            raise ValueError("question_bank.yaml is empty.")

        # Ensure the YAML content is a dictionary
        if not isinstance(data, dict):
            raise TypeError("question_bank.yaml must contain a YAML dictionary.")

        return data

    def _build_prompt(
        self,
        content: str,
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

        return template.format(
            content=content,
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
            raise ValueError("The LLM returned no choices.")

        message = response.choices[0].message

        if message is None:
            raise ValueError("The LLM returned an empty message.")

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
        question_type: str,
        difficulty: str,
        num_questions: int,
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

        prompt = self._build_prompt(
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            num_questions=num_questions,
        )

        raw_response = self._call_llm(prompt)

        # print("\n=== RAW LLM RESPONSE ===")
        # print(raw_response) # to debug/check the raw response from the LLM
        # print("========================\n")

        try:
            response_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e

        try:
            return QuestionBankOutput.model_validate(
                normalize_question_payload(response_json)
            )

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match QuestionBankOutput schema."
            ) from e
