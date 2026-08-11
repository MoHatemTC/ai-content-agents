"""Prompt-template loading failures.

These used to overwrite and rename the *real* ``src/prompts/mentor.yaml`` and
put it back in a ``finally``. A Ctrl-C or a hard crash between the two steps
left the working tree with a corrupted or missing prompt, and two parallel
workers would have raced over the same file. They now point
``explanation_agent_base.PROMPTS_DIR`` at a tmp dir, so the real prompt is never
touched.
"""

import pytest

from src.agents import explanation_agent_base
from src.agents.mentor_agent import MentorAgent
from tests.conftest import CompliantAgentsClient


@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    """Redirect prompt loading at a disposable directory."""
    monkeypatch.setattr(explanation_agent_base, "PROMPTS_DIR", tmp_path)
    return tmp_path


def test_invalid_yaml_is_reported_as_invalid_yaml(prompts_dir):
    """The old version asserted only ``Exception``, which FileNotFoundError,
    TypeError and a typo in the test itself all satisfy."""
    (prompts_dir / "mentor.yaml").write_text(":::: invalid yaml ::::")

    with pytest.raises(ValueError, match="Invalid YAML syntax in mentor.yaml"):
        MentorAgent(client=CompliantAgentsClient())


def test_an_empty_prompt_file_is_reported_as_empty(prompts_dir):
    """``yaml.safe_load`` returns None rather than raising, so without the
    explicit check this surfaced as an AttributeError much later."""
    (prompts_dir / "mentor.yaml").write_text("")

    with pytest.raises(ValueError, match="empty"):
        MentorAgent(client=CompliantAgentsClient())


def test_a_yaml_list_is_reported_as_not_a_mapping(prompts_dir):
    """Valid YAML, wrong shape - the template is indexed by key."""
    (prompts_dir / "mentor.yaml").write_text("- one\n- two\n")

    with pytest.raises(TypeError, match="must contain a YAML dictionary"):
        MentorAgent(client=CompliantAgentsClient())
