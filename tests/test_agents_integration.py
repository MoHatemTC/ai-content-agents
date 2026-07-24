from src.agents.question_bank_agent import QuestionBankAgent
from src.agents.test_help_agent import TestHelpAgent


def test_all_question_agents():

    content = """
    Python has for and while loops.
    """

    qbank = QuestionBankAgent(mock_mode=True)

    result1 = qbank.generate(
        content,
        "mcq",
        "beginner",
        1
    )

    assert len(result1.questions) == 1


    help_agent = TestHelpAgent(mock_mode=True)

    result2 = help_agent.generate(
        content,
        "mcq",
        "beginner",
        1
    )

    assert len(result2.questions) == 1