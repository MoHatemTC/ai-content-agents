from openai import OpenAI

client = OpenAI(
    api_key="sk-3buuEqEUau2qzFvp6TA5dw",
    base_url="https://management.sprints.ai/litellm",
    timeout=60,
)

response = client.chat.completions.create(
    model="FW-Kimi-K2.6",
    messages=[
        {"role": "user", "content": "Say hello in one sentence."}
    ],
)

print(response.choices[0].message.content)