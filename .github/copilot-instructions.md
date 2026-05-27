# demo-helper Agentic Rules

These rules are mandatory for all Copilot agents operating in this repository.

## Non-Negotiable Behavior

1. Never auto-restart playback/capture after user interruption (ESC/cancel/abort).
2. After interruption, report status and wait for explicit user confirmation.
3. For demo capture workflows, generate code snippets and visual artifacts only.
4. Do not execute plan `run_command` steps during screenshot or recording capture flows.
5. Default output mode is `screenshots` unless the user explicitly selects another mode.
6. Always offer output choices as `mp4`, `screenshots`, or `both`.
7. Always remind users:
   - Screenshots support reliable code highlight visibility.
   - Built-in mp4 does not guarantee visible highlight rendering.

## Highlight Reliability

1. Highlight rendering must be applied and settled before screenshot capture.
2. If highlight rendering cannot be confirmed, fail clearly instead of silently continuing.

## User Experience Expectations

1. Prefer deterministic, reproducible runs.
2. Fail fast with actionable errors.
3. Do not hide behavior changes from users; print skipped-step summaries when relevant.

## Chat Preflight UX

1. Before any playback/capture terminal command, present preflight checklist in chat.
2. Include both automated machine checks and manual operator checks in chat.
3. Require explicit user confirmation in chat before execution.
4. Treat terminal-rendered checklist output as secondary, not primary user confirmation UX.
