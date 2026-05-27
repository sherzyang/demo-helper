import json

from openai import OpenAI

from scene_helper.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL

SYSTEM_PROMPT = """\
You are a VS Code demo planner. Given a written description of a topic, \
create a step-by-step coding demo plan that will be auto-typed in VS Code \
and screen recorded for educational purposes.

Output a JSON object with this exact structure:
{
  "title": "Short descriptive title",
  "steps": [
    {"action": "create_file", "filename": "01_topic.py", "content": "..."},
    {"action": "run_command", "command": "python 01_topic.py"},
    {"action": "pause", "seconds": 3}
  ]
}

Available actions:
- "create_file": Opens a new file in VS Code, auto-types the content \
character by character, and saves it.  Fields: filename, content.
  Optional fields for long files: open_line, open_column (1-based) to set \
the viewport before highlight rendering and screenshot capture.
- "run_command": Types and executes a command in the VS Code integrated \
terminal.  Fields: command.
- "pause": Waits for a number of seconds so viewers can read output.  \
Fields: seconds (integer).

Guidelines:
- Break the topic into logical segments, one concept per file.
- Number filenames sequentially: 01_name.py, 02_name.py, etc.
- Keep each file short (10-25 lines) with clear inline comments.
- Use descriptive print() statements so terminal output is self-explanatory.
- After each file, add a run_command to execute it and a pause (3-5 s) for \
viewers to read output.
- If external packages are needed, add a run_command with pip install as \
the very first step followed by a pause.
- Code must be correct, runnable, and educational.
- Add a 2-3 second pause between major segments.
- Do not include markdown, explanation, or anything outside the JSON object.

Highlights (optional):
For create_file steps, you may include a "highlights" array to visually \
emphasize important lines for learners. Each entry has:
- "lines": [startLine, endLine] (1-based, inclusive)
- "style": must be "arrow"
- "color": must be "#90EE9044" (light green)
Example:
  {"action": "create_file", "filename": "01_demo.py", "content": "...",
   "highlights": [{"lines": [3, 5], "style": "arrow", "color": "#90EE9044"}]}
Only use these two visual elements for highlights:
- light green fill (#90EE9044)
- green pointing-finger gutter icon (rendered by arrow style)
Use highlights sparingly — only on the most educationally important lines \
(key patterns, new syntax, critical logic). 1-3 highlights per file maximum.

For long files where highlighted code may be off-screen, set open_line to the \
highlight region (for example open_line: 85).
"""


APPROVED_HIGHLIGHT_COLOR = "#90EE9044"


def _infer_default_highlight_lines(content: str) -> list[int]:
  lines = content.splitlines()
  if not lines:
    return [1, 1]

  first_non_empty = None
  first_meaningful = None
  for idx, raw in enumerate(lines, start=1):
    stripped = raw.strip()
    if not stripped:
      continue
    if first_non_empty is None:
      first_non_empty = idx
    if stripped.startswith(("#", "//", "--")):
      continue
    first_meaningful = idx
    break

  start = first_meaningful or first_non_empty or 1
  end = min(start + 2, max(1, len(lines)))
  return [start, end]


def normalize_plan_highlights(plan: dict) -> dict:
  """Normalize all plan highlights to the approved arrow + light-green style."""
  steps = plan.get("steps", [])
  if not isinstance(steps, list):
    return plan

  for step in steps:
    if not isinstance(step, dict):
      continue
    if step.get("action") != "create_file":
      continue

    highlights = step.get("highlights")
    if not isinstance(highlights, list):
      highlights = []

    normalized = []
    for entry in highlights:
      if not isinstance(entry, dict):
        continue
      lines = entry.get("lines")
      if not (isinstance(lines, list) and len(lines) == 2):
        continue

      try:
        start = int(lines[0])
        end = int(lines[1])
      except (TypeError, ValueError):
        continue

      if start < 1 or end < start:
        continue

      normalized.append(
        {
          "lines": [start, end],
          "style": "arrow",
          "color": APPROVED_HIGHLIGHT_COLOR,
        }
      )

    if normalized:
      step["highlights"] = normalized
      if step.get("open_line") is None:
        step["open_line"] = normalized[0]["lines"][0]
      continue

    default_lines = _infer_default_highlight_lines(step.get("content", ""))
    step["highlights"] = [
      {
        "lines": default_lines,
        "style": "arrow",
        "color": APPROVED_HIGHLIGHT_COLOR,
      }
    ]
    if step.get("open_line") is None:
      step["open_line"] = default_lines[0]

  return plan


def plan_demo(description: str) -> dict:
    """Use OpenAI to break a written description into a demo plan."""
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

    plan = json.loads(response.choices[0].message.content)
    return normalize_plan_highlights(plan)
