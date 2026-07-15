import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LITELLM_API_KEY"),
    base_url=os.getenv("LITELLM_BASE_URL"),
    timeout=60,
)

# LiteLLM configuration is loaded from the .env file.
# Make sure LITELLM_API_KEY, LITELLM_BASE_URL, and DEFAULT_MODEL are set before running this test.

response = client.chat.completions.create(
    model=os.getenv("DEFAULT_MODEL"),
    messages=[
        {
            "role": "user",
            "content": "Say hello in one sentence."
        }
    ],
)

# print(response.choices[0].message.content) 
# print(response) # this will print the entire response object, which includes metadata and other information.
# print(response.model_dump_json(indent=2)) # this will print the entire response in JSON format.