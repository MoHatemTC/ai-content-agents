import pytest
from pydantic import ValidationError

from src.validation.schemas import (
    MentorOutput,
    ConceptOutput,
)


def test_schema_separation():
    """
    Verify that MentorOutput cannot
    be validated as ConceptOutput.
    """

    mentor_response = {
        "explanation": "Python has two loop types.",
        "key_points": [
            "for loop",
            "while loop",
        ],
        "next_steps": [
            "Practice loops.",
        ],
        "references": [
            {
                "segment_id": "chunk_001",
                "text": "Example",
            }
        ],
    }

    mentor = MentorOutput.model_validate(mentor_response)

    assert mentor.explanation == "Python has two loop types."

    with pytest.raises(ValidationError):
        ConceptOutput.model_validate(mentor_response)