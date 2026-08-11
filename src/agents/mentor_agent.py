"""
Mentor Agent

This agent provides supportive explanations for educational content.

Everything it does lives in
:class:`~src.agents.explanation_agent_base.ExplanationAgentBase`, which it
shares with :class:`~src.agents.concept_agent.ConceptAgent`. The two were 85%
byte-identical and had already drifted in how they resolve a
``GroundedContext`` - the same duplication that produced BUG-08/09 in the
question agents. One copy makes that class of defect structurally impossible.
"""

from __future__ import annotations

from dotenv import load_dotenv

from src.agents.explanation_agent_base import ExplanationAgentBase
from src.validation.schemas import MentorOutput

load_dotenv()


class MentorAgent(ExplanationAgentBase):
    """
    AI Mentor Agent.

    Responsibilities:
    - Load mentor prompt template
    - Build the final prompt
    - Send prompt to LiteLLM
    - Validate output using MentorOutput
    """

    prompt_file = "mentor.yaml"
    output_schema = MentorOutput
    agent_name = "mentor_agent"
    output_type = "mentor_explanation"
