from pathlib import Path

import pytest

from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient


def test_invalid_yaml():
    """
    Verify that an invalid YAML prompt
    raises an exception.
    """

    yaml_path = Path("src/prompts/mentor.yaml")

    original = yaml_path.read_text()

    yaml_path.write_text(":::: invalid yaml ::::")

    try:
        with pytest.raises(Exception):
            MentorAgent(client=CompliantAgentsClient())

    finally:
        yaml_path.write_text(original)
