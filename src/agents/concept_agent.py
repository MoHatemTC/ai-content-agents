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
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from src.validation.schemas import ConceptOutput

from pydantic import ValidationError

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

        # Configure mock mode first.
        if mock_mode is None:
            self.mock_mode = (
                os.getenv("MOCK_MODE", "true").lower() == "true"
            )
        else:
            self.mock_mode = mock_mode

        # Load prompt.
        self.prompt = self._load_prompt()

        if not self.mock_mode:
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

        # Check if the YAML file exists
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}"
            )

        try:
            # print(prompt_path) # to debug/check the path to the YAML file temporarily
            with open(prompt_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

        except yaml.YAMLError as e:
            raise ValueError(
                "Invalid YAML syntax in concept.yaml."
            ) from e

        # Check if the YAML file is empty
        if data is None:
            raise ValueError("concept.yaml is empty.")

        # Ensure the YAML content is a dictionary
        if not isinstance(data, dict):
            raise TypeError(
                "concept.yaml must contain a YAML dictionary."
            )

        return data
    

    def _build_prompt(
        self,
        content: str,
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
        
        return template.format(
            content=content,
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



        # print(response.model_dump_json(indent=2))

        content = response.choices[0].message.content

        if not content:
            raise ValueError("The LLM returned an empty response.")

        return content.strip()



    def generate(
        self,
        content: str,
        user_question: Optional[str] = None,
        difficulty: str = "beginner",
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

        Returns:
            Validated ConceptOutput object.
        """

        prompt = self._build_prompt(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
        )
        
        # Temporary mocked response used while LiteLLM is unavailable.
        MOCK_RESPONSE = """
        {
            "definition": "A loop is a programming structure that repeats instructions.",
            "explanation": "Python provides two main loop types: for and while.",
            "key_points": [
                "for loops iterate over sequences.",
                "while loops repeat while a condition is true."
            ],
        "references": [
                {
                    "segment_id": "chunk_001",
                    "text": "Relevant content excerpt."
                }
            ]
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
            return ConceptOutput.model_validate(response_json)

        except ValidationError as e:
            raise ValueError(
                "The LLM response does not match ConceptOutput schema."
            ) from e