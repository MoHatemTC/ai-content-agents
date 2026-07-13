from src.agents.mentor_agent import MentorAgent

agent = MentorAgent()

result = agent.generate(
    content="""
Python is a programming language.
A loop repeats instructions.
There are for loops and while loops.
""",
    user_question="Explain loops.",
    difficulty="beginner",
)

print(result.model_dump_json(indent=2))