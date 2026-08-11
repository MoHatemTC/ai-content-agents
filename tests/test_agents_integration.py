from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent
from tests.conftest import CompliantAgentsClient


def test_all_question_agents():

    content = """
    Python has for and while loops.
    """

    qbank = QuestionBankAgent(client=CompliantAgentsClient())

    result1 = qbank.generate(content, "mcq", "beginner", 1)

    assert len(result1.questions) == 1

    help_agent = TestHelpAgent(client=CompliantAgentsClient())

    result2 = help_agent.generate(content, "mcq", "beginner", 1)

    assert len(result2.questions) == 1
