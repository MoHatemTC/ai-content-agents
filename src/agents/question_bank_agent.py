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
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from src.validation.schemas import QuestionBankOutput

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
            raw_response = MOCK_RESPONSE
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
            return QuestionBankOutput.model_validate(response_json)

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match QuestionBankOutput schema."
            ) from e