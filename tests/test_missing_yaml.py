from pathlib import Path

yaml_path = Path("src/prompts/mentor.yaml")
backup = yaml_path.with_suffix(".bak")

yaml_path.rename(backup)

try:
    from src.agents.mentor_agent import MentorAgent

    MentorAgent(mock_mode=True)

except FileNotFoundError as e:
    print("Missing YAML detected.")
    print(e)

finally:
    backup.rename(yaml_path)