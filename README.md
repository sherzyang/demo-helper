# demo-helper

Create demo-ready VS Code typing videos from natural language prompts.

This repo supports:
- Python demos
- SQL demos
- SQL visual-only demos (no DB connection required)
- C# demos
- Azure DevOps YAML demos
- GitHub Actions YAML demos
- Primary-monitor MP4/WebM recording
- Primary-monitor screenshot capture (one image per `create_file` step)

## Recommended Usage: Agentic (Chat-First)

Use Copilot Chat as the main interface.

How it works:
1. You describe the scenario in chat.
2. The agent asks follow-up questions (scenario, filename, record/play, countdown).
3. The agent generates the plan.
4. The agent runs playback/recording for you.
5. You review the generated video from `recordings/session-*/`.

You do not need to run Python commands manually for normal usage.

## Team Guardrails (Agentic)

These rules are enforced in repository instruction files for shared team behavior:

1. If playback/capture is interrupted by user action (ESC/cancel), do not auto-restart.
2. Wait for explicit user confirmation before any retry.
3. Capture workflows prioritize code snippet generation and screenshots.
4. Do not execute `run_command` plan steps during screenshot/recording capture flows.
5. Default output mode is `screenshots` unless user explicitly chooses otherwise.
6. Always communicate that screenshots reliably show highlights while built-in mp4 may not.

## Prerequisites (Windows)

Required:
1. Python 3.10+
2. VS Code with `code` CLI available on PATH
3. PowerShell
4. ffmpeg available on PATH
5. Azure OpenAI/Foundry credentials

Optional:
1. `sqlcmd` and SQL Server (only for real SQL execution, not needed for visual-only SQL demos)
2. `gradio` (only for optional standalone GUI mode)

## One-Time Setup

From repo root (`C:\demo-helper`):

```powershell
python -m venv .\demos_helper\.venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\demos_helper\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install openai pyautogui python-dotenv runwayml httpx
Set-Location .\scene-helper
python -m pip install -e .
Set-Location ..
```

Create `.env` at repo root:

```env
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://<youropenairesource>.openai.azure.com/openai/v1/
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

## Agentic Scenarios

The chat agent can run these scenarios end-to-end:
1. `python`
2. `sql`
3. `sql-visual`
4. `csharp`
5. `azdo`
6. `gha`

Plan file defaults:
1. `recordings/session-<timestamp>/python/plan.json`
2. `recordings/session-<timestamp>/sql/sqlplan.json`
3. `recordings/session-<timestamp>/sql-visual/sqlplan.visual.json`
4. `recordings/session-<timestamp>/csharp/csharpplan.json`
5. `recordings/session-<timestamp>/azdo/azdoplan.json`
6. `recordings/session-<timestamp>/gha/ghaplan.json`

When using agentic `record-run`, the plan is stored inside the session trace folder by default.

## Recording Environment

**Before running any playback, recording, or screenshot capture:**

- Close all other applications (Outlook, Teams, browsers, etc.)
- Dismiss any system notifications or pop-ups
- Only this VS Code window (where you trigger the agent) should be active on your desktop
- Do not use other apps, mouse, or keyboard while recording/capture is running

This is the same discipline you'd apply to a real human-recorded demo — any foreground window or notification will appear in the capture and can steal focus from the demo VS Code window.

## Recording Behavior (Current Final)

Recording is optimized for reliability:
1. Opens a fresh demo VS Code window.
2. Moves/maximizes it on the primary monitor.
3. Captures primary desktop (scaled to requested output resolution).
4. Supports typing mode (default) and stable mode fallback.
5. Closes demo VS Code window on completion.

Recommended recording defaults:
- `--capture screenshots` (recommended default)
- `--resolution 1920x1280`
- VS Code zoom approximately 110% (configured via workspace settings)
- GitHub Light theme installed and activated automatically
- `--no-focus-lock` when you want to keep using another monitor

MP4 note:
- Built-in MP4 capture does not guarantee visible highlight rendering in the video.
- If highlighted video output is required, run a third-party recorder in parallel.

## Code Highlights (VS Code Extension)

Screenshots can include visual highlights that draw attention to specific lines of code. Highlights are defined per `create_file` step in the plan JSON and rendered live in VS Code by the bundled `demo-highlight` extension.

### How it works

1. Each `create_file` step in a plan can include a `"highlights"` array.
2. After the file is opened and the editor is active, highlight data is written to `.demo-highlights.json` in the workspace.
3. The `demo-highlight` VS Code extension reads that file and applies editor decorations (green background + gutter arrows).
4. The screenshot captures the decorated editor as-is.

### Highlight schema

```json
{
  "action": "create_file",
  "filename": "example.sql",
  "content": "...",
  "highlights": [
    {"lines": [1, 4], "style": "box", "color": "#90EE9044"},
    {"lines": [6, 6], "style": "arrow", "color": "#90EE90"}
  ]
}
```

Fields:
- `lines`: `[startLine, endLine]` — 1-based inclusive line range to highlight.
- `style`: One of `"box"`, `"arrow"`, `"underline"`, `"highlight"`.
- `color`: Optional hex color (e.g. `#90EE90` or `#90EE9044`). Defaults to green.

### Available styles

| Style | Effect |
|-------|--------|
| `box` | Green background fill + solid border around the line range |
| `arrow` | Green gutter arrow icon + green background on each line |
| `underline` | Colored bottom border on each line |
| `highlight` | Background fill only (no border or icon) |

### Color guidance

- Use green (`#90EE9044` for boxes, `#90EE90` for arrows) as the default — readable on both dark and light themes.
- The extension passes the color directly to VS Code's decoration API.

### Where to configure

- **Per-plan**: Edit the `"highlights"` array in your plan JSON file (e.g. `recordings/session-*/sql-visual/sqlplan.visual.json`).
- **AI-generated plans**: The SQL planner (`demos_helper/sql_planner.py`) and general planner (`demos_helper/planner.py`) include highlight instructions in their system prompts.
- **Arrow icon color**: Edit `vscode-demo-highlight/assets/arrow.svg` (currently green `#22C55E`), then rebuild the VSIX.
- **Extension defaults**: In `vscode-demo-highlight/src/extension.ts`, fallback colors are defined in `createDecorationType()`.

### Extension management

```powershell
# Rebuild after changing SVG or extension code
cd vscode-demo-highlight
npm run compile
npx @vscode/vsce package --out demo-highlight.vsix
code --install-extension demo-highlight.vsix --force
# VS Code must reload window to pick up changes
```

### Limitations

- The extension must be installed and VS Code must load it (happens automatically on workspace open).
- Highlights are reliably visible in screenshot capture.
- Built-in MP4 recording does not guarantee visible highlight rendering.
- Maximum ~1-3 highlights per file recommended for clarity.

## Minimal CLI Reference (Fallback)

Use these only if you explicitly want manual execution.

Generate plan:
```powershell
# Let the CLI write to recording artifacts automatically
python -m demos_helper.cli <scenario>-plan "<prompt>"

# Optional explicit output path
python -m demos_helper.cli <scenario>-plan "<prompt>" -o recordings/session-<timestamp>/<scenario>/<plan-file>.json
```

Play plan:
```powershell
python -m demos_helper.cli play <plan-file>
```

Record existing plan:
```powershell
python -m demos_helper.cli record-play <plan-file> --capture mp4 --format mp4 --countdown 8 --resolution 1920x1280 --no-focus-lock
```

Record existing plan and capture screenshots in the same run:
```powershell
python -m demos_helper.cli record-play <plan-file> --capture both --format mp4 --countdown 8 --resolution 1920x1280 --no-focus-lock
```

Capture screenshots only for an existing plan via unified capture mode:
```powershell
python -m demos_helper.cli record-play <plan-file> --capture screenshots --countdown 8 --no-focus-lock
```

Capture screenshots for an existing plan:
```powershell
python -m demos_helper.cli screenshot-play <plan-file> --countdown 8 --no-focus-lock
```

Generate and record in one command:
```powershell
python -m demos_helper.cli record-run <scenario> "<prompt>" --capture mp4 --format mp4 --countdown 8 --resolution 1920x1280 --no-focus-lock
```

Generate once and output both MP4 and screenshots:
```powershell
python -m demos_helper.cli record-run <scenario> "<prompt>" --capture both --format mp4 --countdown 8 --resolution 1920x1280 --no-focus-lock
```

Generate once and output screenshots only:
```powershell
python -m demos_helper.cli record-run <scenario> "<prompt>" --capture screenshots --countdown 8 --no-focus-lock
```

Generate and capture screenshots in one command:
```powershell
python -m demos_helper.cli screenshot-run <scenario> "<prompt>" --countdown 8 --no-focus-lock
```

`--capture` choices for `record-play` and `record-run`:
- `screenshots`: capture one PNG per `create_file` step only (default)
- `mp4`: record video only
- `both`: record MP4 and capture PNG screenshots in one playback run

Preflight confirmation:
- `record-play`, `record-run`, `screenshot-play`, and `screenshot-run` print an operator checklist and require confirmation before capture starts.
- Use `--yes` to skip the confirmation prompt for automated/scripted runs.

## Output Locations

1. `record-play` outputs:
	- Scenario folder: `recordings/session-*/<plan-stem>/`
	- Plan snapshot: `recordings/session-*/<plan-stem>/<plan-file-name>.json`
	- Video: `recordings/session-*/<plan-stem>/playback-*.mp4`
	- Log: `recordings/session-*/<plan-stem>/ffmpeg.log`
2. `record-run` outputs (recommended trace layout):
	- Scenario folder: `recordings/session-*/<scenario>/`
	- Plan: `recordings/session-*/<scenario>/<default-plan-name>.json`
	- Video (when `--capture mp4|both`): `recordings/session-*/<scenario>/playback-*.mp4`
	- Log: `recordings/session-*/<scenario>/ffmpeg.log`
3. `record-run --capture both` outputs:
	- Scenario folder: `recordings/session-*/<scenario>/`
	- Plan: `recordings/session-*/<scenario>/<default-plan-name>.json`
	- Video: `recordings/session-*/<scenario>/playback-*.mp4`
	- Screenshot folder: `recordings/session-*/<scenario>/screenshots/`
	- Images: one PNG per `create_file` step
4. `screenshot-play` outputs:
	- Scenario folder: `recordings/session-*/<plan-stem>/`
	- Plan snapshot: `recordings/session-*/<plan-stem>/<plan-file-name>.json`
	- Screenshot folder: `recordings/session-*/<plan-stem>/screenshots/`
	- Images: `recordings/session-*/<plan-stem>/screenshots/01_<filename>.png`, `02_<filename>.png`, ...
5. `screenshot-run` outputs:
	- Scenario folder: `recordings/session-*/<scenario>/`
	- Plan: `recordings/session-*/<scenario>/<default-plan-name>.json`
	- Screenshot folder: `recordings/session-*/<scenario>/screenshots/`
	- Images: one PNG per `create_file` step
6. Demo workspace files (typed/generated files):
	- `recordings/session-*/demo-workspace/output/`
7. If you pass a custom `--plan-file`, that file is saved too, and a session trace copy is still kept under the scenario folder.

## Troubleshooting

`ModuleNotFoundError: demos_helper`
- Run from repo root: `C:\demo-helper`

Azure 404 errors
- Ensure `.env` uses `/openai/v1/` base URL and deployment name in `OPENAI_CHAT_MODEL`

`ffmpeg` or `code` not found
- Add them to PATH and reopen terminal

Need SQL demo without DB
- Use `sql-visual` scenario

## Optional Standalone GUI

Only if you want a separate app (not chat-first mode):

```powershell
python -m pip install gradio
python -m demos_helper.cli agent-ui
```
