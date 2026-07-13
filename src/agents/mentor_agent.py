"""
Mentor Agent

This agent provides supportive explanations for educational content.
It loads its prompt template from YAML, sends the prompt to the LLM,
and validates the structured response using the MentorOutput schema.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from src.validation.schemas import MentorOutput

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

    def __init__(self) -> None:
        """Initialize the Mentor Agent."""

        self.client = OpenAI(
            api_key=os.getenv("LITELLM_API_KEY"),
            base_url=os.getenv("LITELLM_BASE_URL"),
        )

        self.model = os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6")

        self.prompt = self._load_prompt()


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

        print(f"Loading prompt from: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        print("Loaded YAML:")
        print(data)

        return data

    def _build_prompt(
        self,
        content: str,
        user_question: Optional[str] = "",
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

        content = response.choices[0].message.content

        if not content:
            raise ValueError("The LLM returned an empty response.")

        return content.strip()

    def generate(
        self,
        content: str,
        user_question: Optional[str] = "",
        difficulty: str = "beginner",
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

        prompt = self._build_prompt(
            content=content,
            user_question=user_question,
            difficulty=difficulty,
        )

        raw_response = self._call_llm(prompt)

        try:
            response_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError("The LLM returned invalid JSON.") from e
        
        return MentorOutput.model_validate(response_json)