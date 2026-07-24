from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent


def test_question_bank_prompt_loading():

    agent = QuestionBankAgent(mock_mode=True)

    assert agent.prompt is not None
    assert isinstance(agent.prompt, dict)

    assert "prompt_template" in agent.prompt


def test_test_help_prompt_loading():

    agent = TestHelpAgent(mock_mode=True)

    assert agent.prompt is not None
    assert isinstance(agent.prompt, dict)

    assert "prompt_template" in agent.prompt