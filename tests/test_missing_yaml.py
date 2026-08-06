from pathlib import Path

import pytest

from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient


def test_missing_yaml():
    """
    Verify that a missing YAML prompt
    raises FileNotFoundError.
    """

    yaml_path = Path("src/prompts/mentor.yaml")
    backup = yaml_path.with_suffix(".bak")

    yaml_path.rename(backup)

    try:
        with pytest.raises(FileNotFoundError):
            MentorAgent(client=CompliantAgentsClient())

    finally:
        backup.rename(yaml_path)
