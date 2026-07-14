from pathlib import Path

yaml_path = Path("src/prompts/mentor.yaml")

original = yaml_path.read_text()

yaml_path.write_text(":::: invalid yaml ::::")

try:
    from src.agents.mentor_agent import MentorAgent

    MentorAgent(mock_mode=True)

except Exception as e:
    print("Invalid YAML detected.")
    print(e)

finally:
    yaml_path.write_text(original)