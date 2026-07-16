import json

import pytest


def test_invalid_json():
    """
    Verify that invalid JSON raises a JSONDecodeError.
    """

    invalid_response = """
    {
        "explanation": "Python loops"
    """

    with pytest.raises(json.JSONDecodeError):
        json.loads(invalid_response)