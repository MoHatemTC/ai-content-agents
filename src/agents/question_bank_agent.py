"""
Question Bank Agent

This agent generates grounded educational assessment questions
from uploaded educational content.

Everything it does lives in :class:`~src.agents.question_agent_base.QuestionAgentBase`,
which it shares with :class:`~src.agents.test_help_agent.TestHelpAgent`. The two
were near-identical copies until the Sprint-4 QA pass found that they had
quietly diverged on how they handle an error-shaped HTTP 200 (BUG-08), and that
the divergence silently disabled retries for the one that got it *right*
(BUG-09). One copy of the logic is what stops that happening again.
"""

from __future__ import annotations

from dotenv import load_dotenv

from src.agents.question_agent_base import QuestionAgentBase
from src.validation.schemas import QuestionBankOutput

load_dotenv()


class QuestionBankAgent(QuestionAgentBase):
    """
    AI Question Bank Agent.

    Responsibilities:
    - Load question bank prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using QuestionBankOutput
    """

    prompt_file = "question_bank.yaml"
    output_schema = QuestionBankOutput
    agent_name = "question_bank_agent"
    output_type = "question_bank"
