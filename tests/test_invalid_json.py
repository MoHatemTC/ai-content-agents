import json

invalid_response = """
{
    "explanation": "Python loops"
"""

try:
    json.loads(invalid_response)
except json.JSONDecodeError:
    print("Invalid JSON test passed.")