from src.agents.concept_agent import ConceptAgent
from src.validation.schemas import ConceptOutput


def test_concept_agent_generation():
    """
    Verify that the Concept Agent generates
    a valid ConceptOutput object.
    """

    #agent = ConceptAgent(mock_mode=True)
    agent = ConceptAgent()

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