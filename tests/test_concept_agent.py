from src.agents.concept_agent import ConceptAgent

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

print(result.model_dump_json(indent=2))

print("\nConceptAgent test passed.")