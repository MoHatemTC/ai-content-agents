from src.agents.concept_agent import ConceptAgent
from src.retrieval.models import Chunk, GroundedContext, RetrievalScope, RetrievedChunk
from src.validation.schemas import ConceptOutput
from tests.conftest import CompliantAgentsClient


def test_concept_agent_generation():
    """
    Verify that the Concept Agent generates
    a valid ConceptOutput object.
    """

    agent = ConceptAgent(client=CompliantAgentsClient())

    result = agent.generate(
        content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
        user_question="What is a loop?",
        difficulty="beginner",
    )

    assert isinstance(result, ConceptOutput)

    assert result.definition
    assert result.explanation
    assert len(result.key_points) > 0
    assert len(result.references) > 0

    for reference in result.references:
        assert reference.segment_id
        assert reference.text


def test_concept_agent_generation_with_grounded_context():
    """Verify Concept Agent validates a response against supplied grounding."""
    context = GroundedContext(
        query="What is a loop?",
        scope=RetrievalScope(document_id="document-1"),
        chunks=[
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="chunk_001",
                    document_id="document-1",
                    ordinal=0,
                    text=("Python provides two main loop types: for and while."),
                ),
                score=1.0,
                rank=1,
            )
        ],
    )
    agent = ConceptAgent(client=CompliantAgentsClient())

    prompt = agent._build_prompt(context, difficulty="beginner")
    result = agent.generate(
        content="Raw content remains supported.",
        user_question="What is a loop?",
        difficulty="beginner",
        context=context,
    )

    assert "[chunk_001]" in prompt
    assert context.chunks[0].chunk.text in prompt
    assert isinstance(result, ConceptOutput)
    assert result.references[0].segment_id == "chunk_001"
    assert "Python provides two main loop types" in result.explanation
