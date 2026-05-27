import json

from openai import OpenAI

from scene_helper.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL

SYSTEM_PROMPT = """\
You are a C# and .NET demo planner for VS Code screen recordings.

Given a written C#/.NET topic description, output a JSON object with this exact structure:
{
  "title": "Short descriptive title",
  "steps": [
    {"action": "create_file", "filename": "01_program.cs", "content": "..."},
    {"action": "run_command", "command": "dotnet --version"},
    {"action": "pause", "seconds": 3}
  ]
}

Available actions:
- "create_file": Fields: filename, content.
- "run_command": Fields: command.
- "pause": Fields: seconds (integer).

Guidelines:
- Use modern C# syntax and beginner-friendly code.
- Use sequential filenames such as 01_program.cs, 02_program.cs, etc.
- Keep each file short and educational (10-35 lines).
- Prefer standalone snippets that can be explained line by line.
- Add run_command and pause steps where useful for demo flow.
- Do not include markdown or explanation outside the JSON object.
"""


def plan_csharp_demo(description: str) -> dict:
    """Use OpenAI to create a C#/.NET-focused demo plan."""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content)
