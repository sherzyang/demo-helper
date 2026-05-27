import json

from openai import OpenAI

from scene_helper.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL

BASE_PROMPT = """\
You are a CI/CD YAML demo planner for VS Code screen recordings.

Given a written pipeline topic, output a JSON object with this exact structure:
{
  "title": "Short descriptive title",
  "steps": [
    {"action": "create_file", "filename": "01_pipeline.yml", "content": "..."},
    {"action": "pause", "seconds": 3}
  ]
}

Available actions:
- "create_file": Fields: filename, content.
- "run_command": Fields: command.
- "pause": Fields: seconds (integer).

Guidelines:
- Keep files concise and instructional.
- Prefer create_file + pause actions, and only add run_command if broadly safe.
- Do not include markdown or explanation outside the JSON object.
"""

AZDO_APPEND_PROMPT = """\
Pipeline type: Azure DevOps YAML.
- Use Azure DevOps syntax.
- Include at least one pipeline YAML file named azure-pipelines.yml.
- Optionally include a second file for reusable templates if helpful.
"""

GHA_APPEND_PROMPT = """\
Pipeline type: GitHub Actions YAML.
- Use GitHub Actions syntax.
- Include workflow file path .github/workflows/ci.yml.
- Optionally include a second workflow if helpful.
"""


def plan_pipeline_demo(description: str, pipeline_type: str) -> dict:
    """Use OpenAI to create pipeline-focused demo plans."""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    append_prompt = AZDO_APPEND_PROMPT
    if pipeline_type == "github-actions":
        append_prompt = GHA_APPEND_PROMPT

    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": BASE_PROMPT + "\n\n" + append_prompt},
            {"role": "user", "content": description},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content)
