import json
from unittest.mock import MagicMock

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.grounding import CitationGroundingError
from src.retrieval.models import (
    Chunk,
    GroundedContext,
    RetrievalScope,
    RetrievedChunk,
)
from tests.conftest import CompliantAgentsClient, FakeLLMClient


def grounded_context_double() -> GroundedContext:
    """One retrieved passage, so grounding has something to verify against."""
    return GroundedContext(
        query="What is a loop?",
        scope=RetrievalScope(document_id="document-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk_001",
                    document_id="document-1",
                    ordinal=0,
                    text="Python provides two main loop types: for and while.",
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def test_invalid_json_names_the_agent_that_produced_it():
    """This asserted json.loads raises on bad JSON - i.e. it tested CPython.

    It named no agent and could not fail for any reason connected to this
    codebase. What is worth pinning is that an agent turns a malformed reply
    into an error a person can act on.

    Both replies are malformed because ``generate`` retries once: a model that
    fumbles the output shape usually gets it right on the next sample, and
    live it was fumbling roughly one call in six.
    """
    truncated = '{ "explanation": "cut off'
    agent = MentorAgent(client=FakeLLMClient(truncated, truncated), model="m")

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate("Loops repeat.", "Explain loops.")


def test_a_malformed_reply_is_retried_once():
    """One bad sample must not throw the whole answer away.

    Measured against the live gateway, the model abbreviated ``segment_id`` to
    ``s_id`` on about one call in six; the schema refused it (correctly - the
    strictness is deliberate) and the learner got nothing. The question lane
    already retries once for a wrong question count; this is the same bargain.
    """
    good = json.dumps(
        {
            "explanation": "A loop repeats a block of code.",
            "key_points": ["Loops repeat work"],
            "next_steps": ["Try writing one"],
            "references": [{"segment_id": "seg1", "text": "Loops repeat."}],
            "requires_human_review": True,
        }
    )
    client = FakeLLMClient('{"references": [{"s_id": "seg1"}]}', good)
    agent = MentorAgent(client=client, model="m")

    result = agent.generate("Loops repeat.", "Explain loops.")

    assert result.explanation == "A loop repeats a block of code."
    assert len(client.calls) == 2, "the second sample was never requested"


def test_a_grounding_refusal_is_not_retried():
    """Re-rolling until the model cites something real is not a guarantee.

    A malformed shape is the model failing to comply; an invented citation is
    the model being wrong about the content. Only the first is worth another
    sample.
    """
    uncited = json.dumps(
        {
            "explanation": "A loop repeats a block of code.",
            "key_points": ["Loops repeat work"],
            "next_steps": ["Try writing one"],
            "references": [],
            "requires_human_review": True,
        }
    )
    client = FakeLLMClient(uncited, uncited)
    agent = MentorAgent(client=client, model="m")
    context = grounded_context_double()

    with pytest.raises(CitationGroundingError):
        agent.generate("Loops repeat.", "Explain loops.", context=context)

    assert len(client.calls) == 1, "a refusal must not cost a second call"


def test_mentor_agent_invalid_llm_json_raises_clear_error():
    """MentorAgent translates malformed LLM JSON into a clear ValueError."""
    agent = MentorAgent(client=CompliantAgentsClient())
    response = MagicMock()
    response.choices[0].message.content = "this is not valid json"
    agent.client = MagicMock()
    agent.client.chat.completions.create.return_value = response

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(
            content="Python loops example",
            user_question="Explain loops",
            difficulty="beginner",
        )


def test_concept_agent_invalid_llm_json_raises_clear_error():
    """ConceptAgent translates malformed LLM JSON into a clear ValueError."""
    agent = ConceptAgent(client=CompliantAgentsClient())
    response = MagicMock()
    response.choices[0].message.content = "this is not valid json"
    agent.client = MagicMock()
    agent.client.chat.completions.create.return_value = response

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(
            content="Python loops example",
            user_question="Explain loops",
            difficulty="beginner",
        )
