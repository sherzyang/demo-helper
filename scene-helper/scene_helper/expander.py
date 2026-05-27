from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL

SYSTEM_PROMPT = """\
You are a scene director Create animated, educational videos that clearly visualize concepts and processes.
Keep the output under 800 characters. Write it as a single dense paragraph.
"""


def expand_scene(description: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        max_tokens=300,
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()
