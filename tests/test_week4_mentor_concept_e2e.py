import json

import pytest

from src.agents.concept_agent import ConceptAgent
from src.agents.mentor_agent import MentorAgent
from src.retrieval.models import Chunk, GroundedContext, RetrievedChunk, RetrievalScope
from tests.conftest import CompliantAgentsClient


def _context(*, chunk_id: str = "chunk-1", text: str = "Python has for and while loops.") -> GroundedContext:
    return GroundedContext(
        query="loops",
        scope=RetrievalScope(document_id="doc-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id=chunk_id,
                    document_id="doc-1",
                    ordinal=0,
                    text=text,
                ),
                score=1.0,
                rank=1,
            )
        ],
    )


def test_week4_mentor_grounding_requires_valid_references_and_supported_claims() -> None:
    context = _context(chunk_id="chunk-mentor", text="Python has for and while loops.")
    agent = MentorAgent(client=CompliantAgentsClient())

    prompt = agent._build_prompt(context, user_question="Explain loops.", difficulty="beginner")
    result = agent.generate(
        content="Raw content remains supported.",
        user_question="Explain loops.",
        difficulty="beginner",
        context=context,
    )

    assert "[chunk-mentor]" in prompt
    assert context.chunks[0].chunk.text in prompt
    assert result.references[0].segment_id == "chunk-mentor"


def test_week4_concept_grounding_requires_valid_references_and_supported_claims() -> None:
    context = _context(chunk_id="chunk-concept", text="Python has for and while loops.")
    agent = ConceptAgent(client=CompliantAgentsClient())

    prompt = agent._build_prompt(context, user_question="What is a loop?", difficulty="beginner")
    result = agent.generate(
        content="Raw content remains supported.",
        user_question="What is a loop?",
        difficulty="beginner",
        context=context,
    )

    assert "[chunk-concept]" in prompt
    assert context.chunks[0].chunk.text in prompt
    assert result.references[0].segment_id == "chunk-concept"


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_week4_difficulty_control_reaches_the_model(agent_class: type) -> None:
    """The requested difficulty has to arrive in the prompt.

    This used to assert that an "advanced" explanation came back longer than a
    "beginner" one - but the only thing producing those strings was the mock,
    which was written to return progressively longer text. It tested the
    fixture. What the agent is actually responsible for is asking for the depth
    the caller requested; what the model then writes is the model's business.
    """
    client = CompliantAgentsClient()
    agent = agent_class(client=client)

    for difficulty in ("beginner", "intermediate", "advanced"):
        agent.generate(content="Python has for and while loops.", difficulty=difficulty)
        prompt = client.calls[-1]["messages"][0]["content"]
        assert difficulty in prompt, f"{difficulty!r} never reached the model"


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_week4_outputs_default_to_human_review(agent_class: type) -> None:
    agent = agent_class(client=CompliantAgentsClient())
    result = agent.generate(content="Python has for and while loops.", difficulty="beginner")

    assert result.requires_human_review is True


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_week4_grounded_generation_retains_human_review(agent_class: type) -> None:
    context = _context(chunk_id="chunk-review", text="Python has for loops.")
    agent = agent_class(client=CompliantAgentsClient())

    result = agent.generate(
        content="content",
        user_question="Explain loops.",
        difficulty="advanced",
        context=context,
    )

    assert result.requires_human_review is True


def test_week4_support_check_blocks_off_content_mentor_claims(monkeypatch) -> None:
    context = _context(chunk_id="chunk-mentor", text="Python has for loops.")
    agent = MentorAgent(client=CompliantAgentsClient())

    def fake_call_llm(_: str, **kwargs) -> str:
        return json.dumps(
            {
                "explanation": "Python automatically parallelizes loops.",
                "key_points": ["Python has for loops."],
                "next_steps": ["Re-read the loop section."],
                "references": [{"segment_id": "chunk-mentor", "text": "Python has for loops."}],
                "requires_human_review": True,
            }
        )

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

    # A support failure is a warning now, not a rejection: the overlap
    # heuristic rejected 5 of 20 correct live generations, so raising on it
    # meant grounding was switched off entirely. The output is flagged for the
    # reviewer instead - see ExplanationAgentBase._enforce_grounding.
    agent.generate(
        content="content",
        user_question="Explain loops.",
        difficulty="beginner",
        context=context,
    )

    assert agent._grounding_warnings, "the off-content claim was not flagged"
    assert any(
        "parallelizes" in w for w in agent._grounding_warnings
    ), agent._grounding_warnings


def test_week4_support_check_blocks_off_content_concept_claims(monkeypatch) -> None:
    context = _context(chunk_id="chunk-concept", text="Python has for loops.")
    agent = ConceptAgent(client=CompliantAgentsClient())

    def fake_call_llm(_: str, **kwargs) -> str:
        return json.dumps(
            {
                "definition": "Loops are compiled into machine code automatically.",
                "explanation": "Python has for loops.",
                "key_points": ["for loops"],
                "references": [{"segment_id": "chunk-concept", "text": "Python has for loops."}],
                "requires_human_review": True,
            }
        )

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

    # Same contract change as the mentor case above: flagged, not rejected.
    agent.generate(
        content="content",
        user_question="What is a loop?",
        difficulty="beginner",
        context=context,
    )

    assert agent._grounding_warnings, "the off-content definition was not flagged"
    assert any(
        "machine code" in w for w in agent._grounding_warnings
    ), agent._grounding_warnings


@pytest.mark.parametrize("agent_class", [MentorAgent, ConceptAgent])
def test_week4_reference_verification_blocks_fabricated_segment_ids(
    agent_class: type, monkeypatch
) -> None:
    context = _context(chunk_id="chunk-real", text="Python has for loops.")
    agent = agent_class(client=CompliantAgentsClient())

    def fake_call_llm(_: str, **kwargs) -> str:
        payload: dict[str, object]
        if agent_class is MentorAgent:
            payload = {
                "explanation": "Python has for loops.",
                "key_points": ["for loops"],
                "next_steps": ["Practice loops."],
                "references": [{"segment_id": "chunk-fake", "text": "Fabricated"}],
                "requires_human_review": True,
            }
        else:
            payload = {
                "definition": "A loop repeats instructions.",
                "explanation": "Python has for loops.",
                "key_points": ["for loops"],
                "references": [{"segment_id": "chunk-fake", "text": "Fabricated"}],
                "requires_human_review": True,
            }
        return json.dumps(payload)

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

    with pytest.raises(ValueError, match="not grounded"):
        agent.generate(
            content="content",
            user_question="question",
            difficulty="beginner",
            context=context,
        )
