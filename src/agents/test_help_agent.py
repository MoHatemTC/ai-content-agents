"""
Test Help Agent

This agent generates grounded practice questions to help learners
prepare for assessments on uploaded educational content.

Everything it does lives in :class:`~src.agents.question_agent_base.QuestionAgentBase`,
which it shares with :class:`~src.agents.question_bank_agent.QuestionBankAgent`.
This agent is the one that had BUG-08: it indexed ``response.choices[0]``
without checking, so a saturated provider surfaced as
``TypeError: 'NoneType' object is not subscriptable``. Its sibling guarded the
same case correctly. Sharing the implementation is the fix that keeps them from
drifting apart again.
"""

from __future__ import annotations

from dotenv import load_dotenv

from src.agents.question_agent_base import QuestionAgentBase
from src.validation.schemas import TestHelpOutput

load_dotenv()

# Stops pytest collecting the Test*-prefixed class as a test case.
__test__ = False


class TestHelpAgent(QuestionAgentBase):
    """
    AI Test Help Agent.

    Responsibilities:
    - Load test help prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using TestHelpOutput
    """

    __test__ = False

    prompt_file = "test_help.yaml"
    output_schema = TestHelpOutput
    agent_name = "test_help_agent"
    output_type = "test_help"
