from pydantic import ValidationError

from src.validation.schemas import (
    MentorOutput,
    ConceptOutput,
)

mentor_response = {
    "explanation": "Python has two loop types.",
    "key_points": [
        "for loop",
        "while loop"
    ],
    "next_steps": [
        "Practice loops."
    ],
    "references": [
        "chunk_001"
    ],
}

# This should pass.
MentorOutput.model_validate(mentor_response)

try:
    # This should fail because ConceptOutput
    # requires a definition instead of next_steps.
    ConceptOutput.model_validate(mentor_response)

except ValidationError:
    print("Schema separation test passed.")