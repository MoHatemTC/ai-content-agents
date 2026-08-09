"""
Concept Explanation Agent

This agent defines and explains a single concept from educational content.

Everything it does lives in
:class:`~src.agents.explanation_agent_base.ExplanationAgentBase`, which it
shares with :class:`~src.agents.mentor_agent.MentorAgent`. This agent is the one
that relied on ``_build_prompt``'s ``GroundedContext`` branch while Mentor
resolved the context itself - so breaking that branch would have regressed this
agent silently while Mentor kept working and every test passed.
"""

from __future__ import annotations

from dotenv import load_dotenv

from src.agents.explanation_agent_base import ExplanationAgentBase
from src.validation.schemas import ConceptOutput

load_dotenv()


class ConceptAgent(ExplanationAgentBase):
    """
    AI Concept Explanation Agent.

    Responsibilities:
    - Load concept prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using ConceptOutput
    """

    prompt_file = "concept.yaml"
    output_schema = ConceptOutput
    agent_name = "concept_agent"
    output_type = "concept_explanation"
