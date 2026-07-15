from src.agents.mentor_agent import MentorAgent

# ==========================================
# MOCK MODE
# Forces the agent to use the hardcoded
# mock response instead of calling LiteLLM.
# Use this while developing or when the
# API is unavailable.
# ==========================================
# agent = MentorAgent(mock_mode=True)  

# ==========================================
# REAL API MODE
# Forces the agent to call LiteLLM.
# This ignores the MOCK_MODE value in .env.
# Uncomment when the API is working.
# ==========================================
# agent = MentorAgent(mock_mode=False)


# ==========================================
# ENVIRONMENT MODE
# Uses the MOCK_MODE value from .env.
# If MOCK_MODE=true  -> uses mock response.
# If MOCK_MODE=false -> uses LiteLLM.
# ==========================================
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

print("\n MentorAgent test passed.")