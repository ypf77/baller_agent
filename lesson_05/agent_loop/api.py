from agent_loop.config import client, MODEL, SYSTEM
from agent_loop.tools import TOOLS


def call_deepseek(messages: list):
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            *messages
        ],
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=8000,
        temperature=0.0,
    )
    return response.choices[0].message
