import os

# Simulate missing API key
os.environ.pop("LITELLM_API_KEY", None)

try:
    from src.agents.mentor_agent import MentorAgent

    MentorAgent(mock_mode=True)

except ValueError as e:
    print("Missing environment variable detected.")
    print(e)