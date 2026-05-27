import json

from openai import OpenAI

from scene_helper.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL

SYSTEM_PROMPT = """\
You are a SQL demo planner for VS Code screen recordings.

Given a written SQL topic description, output a JSON object with this exact structure:
{
  "title": "Short descriptive title",
  "steps": [
    {"action": "create_file", "filename": "01_topic.sql", "content": "..."},
    {"action": "run_command", "command": "sqlcmd -S localhost -E -d master -i output\\01_topic.sql"},
    {"action": "pause", "seconds": 3}
  ]
}

Available actions:
- "create_file": Fields: filename, content.
- "run_command": Fields: command.
- "pause": Fields: seconds (integer).

SQL demo guidelines:
- Use SQL Server T-SQL syntax.
- Use sequential .sql filenames: 01_name.sql, 02_name.sql, etc.
- Keep scripts concise and educational (10-40 lines each).
- Prefer idempotent setup patterns where possible (IF DB_ID... / IF OBJECT_ID...).
- If creating objects, include verification queries (SELECT, sys.objects checks).
- After each file, include a run_command and a pause (3-5 seconds).
- Use `sqlcmd` in run_command examples.
- Assume Windows auth by default in examples: `-E`.
- Do not include markdown or explanation outside the JSON object.

Highlights (optional):
For create_file steps, you may include a "highlights" array to visually \
emphasize important lines for learners. Each entry has:
- "lines": [startLine, endLine] (1-based, inclusive)
- "style": "box" | "arrow" | "underline" | "highlight"
- "color": optional hex with alpha (e.g. "#FFD70066")
Example:
  {"action": "create_file", "filename": "01_demo.sql", "content": "...",
   "highlights": [{"lines": [3, 5], "style": "box"}, {"lines": [10, 10], "style": "arrow"}]}
Use highlights sparingly — only on the most educationally important lines \
(key syntax, critical clauses, new concepts). 1-3 highlights per file maximum.
"""

VISUAL_ONLY_APPEND_PROMPT = """\
Additional requirement: visual-only mode is enabled.
- Do not include any run_command actions.
- Use only create_file and pause actions.
- Add short pause actions (2-4 seconds) between files.
"""


def plan_sql_demo(description: str, visual_only: bool = False) -> dict:
    """Use OpenAI to create a SQL-focused demo plan."""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    system_prompt = SYSTEM_PROMPT
    if visual_only:
        system_prompt = SYSTEM_PROMPT + "\n\n" + VISUAL_ONLY_APPEND_PROMPT

    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": description},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content)
