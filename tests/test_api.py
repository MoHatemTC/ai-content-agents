from unittest.mock import MagicMock

from src.agents.mentor_agent import MentorAgent


def test_api_mock_response():
    """
    Verify that the API client can be mocked
    without making a real network request.
    """

    agent = MentorAgent(mock_mode=True)

    mock_response = MagicMock()

    mock_response.choices[0].message.content = """
    {
        "explanation": "Loops repeat instructions.",
        "key_points": [
            "Loops avoid repeating code."
        ],
        "next_steps": [
            "Practice writing loops."
        ],
        "references": [
            {
                "segment_id": "seg1",
                "text": "A loop repeats instructions."
            }
        ]
    }
    """

    agent.client = MagicMock()
    agent.client.chat.completions.create.return_value = mock_response

    result = agent._call_llm("Explain loops")

    assert result is not None
    assert "Loops repeat instructions" in result