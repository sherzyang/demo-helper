import json
import os
import re
import shutil
import subprocess
import threading
import time
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Tuple
from ctypes import wintypes

from .csharp_planner import plan_csharp_demo
from .pipeline_planner import plan_pipeline_demo
from .planner import normalize_plan_highlights, plan_demo
from .player import play_demo
from .sql_planner import plan_sql_demo


def _visual_only_plan(plan: Dict) -> tuple[Dict, int]:
    """Return a copy of plan without run_command steps for capture-safe playback."""
    steps = plan.get("steps", [])
    filtered_steps = []
    skipped = 0
    for step in steps:
        if step.get("action") == "run_command":
            skipped += 1
            continue
        filtered_steps.append(step)

    return {
        "title": plan.get("title", "Untitled"),
        "steps": filtered_steps,
    }, skipped


def _enable_dpi_awareness() -> None:
    # Align Win32 coordinates with physical pixels used by ffmpeg capture.
    # Try the most modern API first, then progressively older fallbacks.
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_plan_name(scenario: str) -> str:
    mapping = {
        "python": "plan.json",
        "sql": "sqlplan.json",
        "sql-visual": "sqlplan.visual.json",
        "csharp": "csharpplan.json",
        "azdo": "azdoplan.json",
        "gha": "ghaplan.json",
    }
    return mapping[scenario]


def _sanitize_for_filename(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return sanitized or "file"


def build_plan_for_scenario(scenario: str, prompt: str) -> Dict:
    if scenario == "python":
        return normalize_plan_highlights(plan_demo(prompt))
    if scenario == "sql":
        return normalize_plan_highlights(plan_sql_demo(prompt, visual_only=False))
    if scenario == "sql-visual":
        return normalize_plan_highlights(plan_sql_demo(prompt, visual_only=True))
    if scenario == "csharp":
        return normalize_plan_highlights(plan_csharp_demo(prompt))
    if scenario == "azdo":
        return normalize_plan_highlights(
            plan_pipeline_demo(prompt, pipeline_type="azure-devops")
        )
    if scenario == "gha":
        return normalize_plan_highlights(
            plan_pipeline_demo(prompt, pipeline_type="github-actions")
        )

    raise ValueError(f"Unsupported scenario: {scenario}")


def save_plan(plan: Dict, plan_file: Path) -> None:
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)


def _ensure_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is required but was not found on PATH.")
    return path


# ---------------------------------------------------------------------------
# Highlight support
# ---------------------------------------------------------------------------

_HIGHLIGHTS_FILENAME = ".demo-highlights.json"
_DEMO_HIGHLIGHT_EXT_DIR = Path(__file__).resolve().parent.parent / "vscode-demo-highlight"
_PREFERRED_THEME_EXTENSION_ID = "GitHub.github-vscode-theme"
_PREFERRED_THEME_NAME = "GitHub Light"





def _write_highlights(workspace_dir: Path, highlights: list) -> None:
    """Write highlight entries to the workspace so the extension can render them."""
    highlights_file = workspace_dir / _HIGHLIGHTS_FILENAME
    highlights_file.write_text(json.dumps(highlights, indent=2), encoding="utf-8")


def _clear_highlights(workspace_dir: Path) -> None:
    """Clear active highlights by writing an empty array."""
    _write_highlights(workspace_dir, [])


def _apply_step_highlights(workspace_dir: Path, step: dict) -> None:
    """Apply highlights defined in a plan step, if any."""
    normalized_step = normalize_plan_highlights(
        {
            "steps": [
                {
                    "action": step.get("action"),
                    "highlights": step.get("highlights"),
                }
            ]
        }
    )["steps"][0]
    highlights = normalized_step.get("highlights")
    if highlights:
        _write_highlights(workspace_dir, highlights)
    else:
        _clear_highlights(workspace_dir)


def _install_demo_highlight_extension() -> None:
    """Install the demo-highlight VS Code extension if a VSIX is available."""
    vsix = _DEMO_HIGHLIGHT_EXT_DIR / "demo-highlight.vsix"
    if not vsix.exists():
        return
    code_path = shutil.which("code")
    if not code_path:
        return
    try:
        subprocess.run(
            [code_path, "--install-extension", str(vsix), "--force"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _is_vscode_extension_installed(extension_id: str) -> bool:
    code_path = shutil.which("code")
    if not code_path:
        return False
    try:
        result = subprocess.run(
            [code_path, "--list-extensions"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            return False
        installed = {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
        return extension_id.lower() in installed
    except Exception:
        return False


def _ensure_preferred_theme_installed() -> None:
    code_path = shutil.which("code")
    if not code_path:
        return
    if _is_vscode_extension_installed(_PREFERRED_THEME_EXTENSION_ID):
        return
    try:
        subprocess.run(
            [code_path, "--install-extension", _PREFERRED_THEME_EXTENSION_ID, "--force"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def validate_capture_environment(
    expected_resolution: str = "1920x1280",
    require_highlight_extension: bool = False,
) -> dict:
    """Validate local machine prerequisites before capture starts."""
    _enable_dpi_awareness()

    code_ok = shutil.which("code") is not None
    ffmpeg_ok = shutil.which("ffmpeg") is not None

    # Proactively ensure required extensions are present before checking status.
    _ensure_preferred_theme_installed()
    if require_highlight_extension:
        _install_demo_highlight_extension()

    theme_ext_ok = _is_vscode_extension_installed(_PREFERRED_THEME_EXTENSION_ID)
    highlight_ext_ok = _is_vscode_extension_installed("demo-helper.demo-highlight")

    try:
        expected_w, expected_h = expected_resolution.lower().split("x", 1)
        min_w = int(expected_w)
        min_h = int(expected_h)
    except (TypeError, ValueError):
        min_w, min_h = 1920, 1280

    x, y, screen_w, screen_h = _get_primary_desktop_region()
    resolution_ok = screen_w >= min_w and screen_h >= min_h

    checks = [
        {
            "name": "VS Code CLI available",
            "passed": code_ok,
            "detail": "code CLI is on PATH" if code_ok else "Install/configure the `code` CLI",
        },
        {
            "name": "FFmpeg available",
            "passed": ffmpeg_ok,
            "detail": "ffmpeg is on PATH" if ffmpeg_ok else "Install/configure ffmpeg on PATH",
        },
        {
            "name": "Primary display resolution",
            "passed": resolution_ok,
            "detail": (
                f"Detected {screen_w}x{screen_h}, target >= {min_w}x{min_h}"
                if resolution_ok
                else f"Detected {screen_w}x{screen_h}, target requires >= {min_w}x{min_h}"
            ),
        },
        {
            "name": "GitHub Light theme extension",
            "passed": theme_ext_ok,
            "detail": (
                "GitHub.github-vscode-theme installed"
                if theme_ext_ok
                else "Could not verify GitHub.github-vscode-theme installation"
            ),
        },
    ]

    if require_highlight_extension:
        checks.append(
            {
                "name": "Demo highlight extension",
                "passed": highlight_ext_ok,
                "detail": (
                    "demo-helper.demo-highlight installed"
                    if highlight_ext_ok
                    else "Could not verify demo-helper.demo-highlight installation"
                ),
            }
        )

    return {
        "checks": checks,
        "all_passed": all(item["passed"] for item in checks),
        "screen_region": [x, y, screen_w, screen_h],
        "configured_theme": _PREFERRED_THEME_NAME,
        "configured_zoom_level": 0.5,
    }


def _prepare_demo_workspace(session_dir: Path) -> Path:
    workspace_dir = session_dir / "demo-workspace"
    settings_dir = workspace_dir / ".vscode"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    settings_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "workbench.startupEditor": "none",
        "workbench.tips.enabled": False,
        "workbench.welcome.enabled": False,
        "window.zoomLevel": 0.5,
        "workbench.colorTheme": _PREFERRED_THEME_NAME,
        "editor.minimap.enabled": False,
        "breadcrumbs.enabled": False,
        "files.autoSave": "afterDelay",
        "files.autoSaveDelay": 200,
        "workbench.activityBar.visible": False,
        "workbench.statusBar.visible": False,
        "extensions.ignoreRecommendations": True,
        "security.workspace.trust.enabled": False,
    }
    with open(settings_dir / "settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

    return workspace_dir


def _create_session_dir(root: Path) -> Path:
    session_dir = root / "recordings" / f"session-{_timestamp()}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _launch_vscode_window(workspace_dir: Path) -> None:
    _install_demo_highlight_extension()
    _ensure_preferred_theme_installed()
    code_path = _ensure_tool("code")
    subprocess.Popen(
        [
            code_path,
            "-n",
            str(workspace_dir),
            "--maximized",
            "--skip-release-notes",
            "--skip-add-to-recently-opened",
            "--disable-workspace-trust",
        ],
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _build_ffmpeg_cmd(
    video_file: Path,
    resolution: str,
    input_target: str = "desktop",
    capture_region: Tuple[int, int, int, int] | None = None,
) -> list[str]:
    ffmpeg_path = _ensure_tool("ffmpeg")
    width, height = resolution.lower().split("x", 1)
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )
    base: list[str] = [
        ffmpeg_path,
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        "30",
    ]

    if capture_region is not None and input_target == "desktop":
        x, y, w, h = capture_region
        base.extend([
            "-offset_x", str(x),
            "-offset_y", str(y),
            "-video_size", f"{w}x{h}",
        ])

    base.extend([
        "-i",
        input_target,
        "-vf",
        scale_filter,
    ])

    if video_file.suffix.lower() == ".mp4":
        return base + [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_file),
        ]

    return base + [
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuv420p",
        str(video_file),
    ]


def _start_recording(
    video_file: Path,
    resolution: str,
    ffmpeg_log_file: Path,
) -> subprocess.Popen:
    _ensure_tool("ffmpeg")
    video_file.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_log_file.parent.mkdir(parents=True, exist_ok=True)

    # Reliable default for multi-monitor setups: capture only primary monitor desktop.
    capture_region = _get_primary_desktop_region()

    log_handle = open(ffmpeg_log_file, "w", encoding="utf-8")
    try:
        cmd = _build_ffmpeg_cmd(
            video_file,
            resolution,
            input_target="desktop",
            capture_region=capture_region,
        )
        log_handle.write("\n=== ffmpeg capture: primary-desktop ===\n")
        log_handle.flush()

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            shell=False,
        )

        time.sleep(0.8)
        if proc.poll() is None:
            print("Recording capture method: primary-desktop")
            return proc

        raise RuntimeError(
            f"ffmpeg failed to start recording (exit code {proc.returncode}). "
            f"See log: {ffmpeg_log_file}"
        )
    finally:
        log_handle.close()


def _get_primary_desktop_region() -> Tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return (0, 0, width, height)


def _position_vscode_on_primary(title_hint: str) -> None:
    user32 = ctypes.windll.user32

    hwnd = None
    # Allow window creation/render latency and only target the demo workspace window.
    for _ in range(12):
        hwnd = _find_vscode_window_hwnd(title_hint, strict_workspace=True)
        if hwnd is not None:
            break
        time.sleep(0.2)

    if hwnd is None:
        return

    width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    SW_RESTORE = 9
    SW_MAXIMIZE = 3
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040

    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, 0, 0, 0, width, height, SWP_NOZORDER | SWP_SHOWWINDOW)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)


def _find_vscode_window_hwnd(title_hint: str, strict_workspace: bool = False) -> int | None:
    user32 = ctypes.windll.user32
    title_hint_l = title_hint.lower()
    workspace_hint = title_hint_l.split(" - ", 1)[0]
    found: dict[str, int | None] = {"exact": None, "fallback": None}

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @enum_proc
    def _callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value.lower()
        if "visual studio code" not in title:
            return True

        if strict_workspace and workspace_hint not in title and title_hint_l not in title:
            return True

        if found["fallback"] is None:
            found["fallback"] = hwnd

        if workspace_hint in title or title_hint_l in title:
            found["exact"] = hwnd
            return False

        return True

    for _ in range(10):
        user32.EnumWindows(_callback, 0)
        if found["exact"] is not None:
            return int(found["exact"])
        if found["fallback"] is not None:
            return int(found["fallback"])
        time.sleep(0.15)

    return None


def _close_vscode_window(title_hint: str) -> None:
    hwnd = _find_vscode_window_hwnd(title_hint, strict_workspace=True)
    if hwnd is not None:
        # WM_CLOSE
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
        time.sleep(0.4)

    # Fallback close path when window title changed and HWND matching missed.
    workspace_hint = title_hint.split(" - ", 1)[0]
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"if ($ws.AppActivate('{workspace_hint}')) {{ $ws.SendKeys('%{{F4}}') }}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _activate_vscode_window(title_hint: str) -> None:
    activated = False

    hwnd = _find_vscode_window_hwnd(title_hint, strict_workspace=True)
    if hwnd is not None:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        activated = True

    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$ok = $ws.AppActivate('{title_hint}'); "
        "if (-not $ok) { Start-Sleep -Milliseconds 50; $null = $ws.AppActivate('Visual Studio Code') }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Let focus settle before sending keystrokes for the next step.
    if activated:
        time.sleep(0.08)


def _prepare_clean_view_shortcuts() -> None:
    # Use native VS Code shortcuts to reduce clutter in the recording window.
    # Ctrl+B toggles Side Bar, Ctrl+J toggles panel, Ctrl+Shift+P opens command palette.
    import pyautogui

    pyautogui.press("escape")
    time.sleep(0.1)

    pyautogui.hotkey("ctrl", "b")
    time.sleep(0.2)

    pyautogui.hotkey("ctrl", "j")
    time.sleep(0.2)

    # Hide activity/status bars via commands for a cleaner code-only look.
    pyautogui.hotkey("ctrl", "shift", "p")
    time.sleep(0.3)
    pyautogui.write("View: Toggle Activity Bar Visibility", interval=0.01)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.25)

    pyautogui.hotkey("ctrl", "shift", "p")
    time.sleep(0.3)
    pyautogui.write("View: Toggle Status Bar Visibility", interval=0.01)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.25)

    # Open Explorer view and focus editor area.
    pyautogui.hotkey("ctrl", "shift", "e")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "1")
    time.sleep(0.2)


def _focus_keeper(stop_event: threading.Event, title_hint: str, interval_seconds: float = 0.7) -> None:
    while not stop_event.is_set():
        _activate_vscode_window(title_hint)
        stop_event.wait(interval_seconds)


def _is_escape_pressed() -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)


def _check_abort() -> None:
    if _is_escape_pressed():
        raise KeyboardInterrupt("Playback aborted by ESC key")


def _open_file_in_vscode(file_path: Path, line: int = 1, column: int = 1) -> None:
    code_path = _ensure_tool("code")
    line = max(1, int(line))
    column = max(1, int(column))
    subprocess.run(
        [code_path, "-r", "-g", f"{file_path}:{line}:{column}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _resolve_open_position(step: dict) -> Tuple[int, int]:
    """Pick where to open the file for viewport-aware screenshots.

    Priority:
    1) explicit open_line/open_column from plan
    2) first highlight start line
    3) default line 1, column 1
    """
    line = step.get("open_line")
    col = step.get("open_column")

    if line is None:
        highlights = step.get("highlights")
        if isinstance(highlights, list):
            for entry in highlights:
                if not isinstance(entry, dict):
                    continue
                lines = entry.get("lines")
                if isinstance(lines, list) and len(lines) == 2:
                    try:
                        line = int(lines[0])
                        break
                    except (TypeError, ValueError):
                        continue

    try:
        line_num = max(1, int(line)) if line is not None else 1
    except (TypeError, ValueError):
        line_num = 1

    try:
        col_num = max(1, int(col)) if col is not None else 1
    except (TypeError, ValueError):
        col_num = 1

    return line_num, col_num


def _wait_for_editor(workspace_dir: Path, filename: str, timeout: float = 20.0) -> bool:
    """Poll the extension log until VS Code confirms the file is active."""
    log_file = workspace_dir / ".demo-highlight-log.txt"
    start = time.time()
    while time.time() - start < timeout:
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8")
                for line in reversed(content.splitlines()):
                    if "EditorChange:" in line and filename in line:
                        return True
            except OSError:
                pass
        time.sleep(0.3)
    return False


def _wait_for_highlight_apply(
    workspace_dir: Path,
    filename: str,
    since_ts: float,
    timeout: float = 8.0,
) -> bool:
    """Wait until extension logs a highlight apply event for the target file."""
    log_file = workspace_dir / ".demo-highlight-log.txt"
    target = filename.lower()
    end = time.time() + timeout

    while time.time() < end:
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8")
            except OSError:
                time.sleep(0.2)
                continue

            for line in reversed(content.splitlines()):
                if "applyHighlights: applying" not in line:
                    continue
                if target not in line.lower():
                    continue

                try:
                    stamp = line.split("]", 1)[0].lstrip("[")
                    event_ts = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                except Exception:
                    event_ts = 0.0

                if event_ts >= since_ts:
                    return True

        time.sleep(0.2)

    return False


def _warmup_vscode_editor(workspace_dir: Path) -> None:
    """Open a dummy file to warm up VS Code's editor rendering pipeline.

    The very first editor tab opened in a new VS Code window has a rendering
    bug where setDecorations calls don't visually paint. Opening a throwaway
    file first and waiting for VS Code to confirm it's active ensures the
    rendering pipeline is initialized.
    """
    warmup_file = workspace_dir / ".vscode" / "warmup.txt"
    warmup_file.write_text("# warm-up\n", encoding="utf-8")
    _open_file_in_vscode(warmup_file, line=1, column=1)
    _wait_for_editor(workspace_dir, "warmup.txt")
    time.sleep(1.0)


def _run_plan_stable(plan: Dict, workspace_dir: Path, title_hint: str) -> None:
    steps = plan.get("steps", [])
    print(f"\nDemo: {plan.get('title', 'Untitled')}")
    print(f"Steps: {len(steps)}")
    print("\nStable mode: deterministic file writes + visual file opening in VS Code")

    output_dir = workspace_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    _warmup_vscode_editor(workspace_dir)

    for idx, step in enumerate(steps, 1):
        _check_abort()
        _activate_vscode_window(title_hint)

        action = step.get("action")
        if action == "create_file":
            rel_name = step["filename"]
            target = output_dir / rel_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step.get("content", ""), encoding="utf-8")
            print(f"[{idx}/{len(steps)}] create_file  {rel_name}")
            open_line, open_col = _resolve_open_position(step)
            _open_file_in_vscode(target, line=open_line, column=open_col)
            _wait_for_editor(workspace_dir, target.name)
            time.sleep(2.0)  # Let VS Code settle after confirmed open
            _apply_step_highlights(workspace_dir, step)
            time.sleep(1.5)  # Wait for extension to render highlights
            _apply_step_highlights(workspace_dir, step)  # Re-trigger file watcher
            time.sleep(0.5)
        elif action == "run_command":
            command = step.get("command", "")
            print(f"[{idx}/{len(steps)}] run_command   {command}")
            subprocess.run(
                command,
                shell=True,
                cwd=workspace_dir,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.8)
        elif action == "pause":
            secs = int(step.get("seconds", 2))
            print(f"[{idx}/{len(steps)}] pause         {secs}s")
            for _ in range(secs):
                _check_abort()
                time.sleep(1)
        else:
            print(f"[{idx}/{len(steps)}] unknown action '{action}', skipping")

    _clear_highlights(workspace_dir)
    print("\nDemo playback complete!")


def _run_plan_stable_with_hook(
    plan: Dict,
    workspace_dir: Path,
    title_hint: str,
    post_step_hook: Callable[[dict, int, int], None] | None = None,
) -> None:
    steps = plan.get("steps", [])
    print(f"\nDemo: {plan.get('title', 'Untitled')}")
    print(f"Steps: {len(steps)}")
    print("\nStable mode: deterministic file writes + visual file opening in VS Code")

    output_dir = workspace_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    _warmup_vscode_editor(workspace_dir)

    for idx, step in enumerate(steps, 1):
        _check_abort()
        _activate_vscode_window(title_hint)

        action = step.get("action")
        if action == "create_file":
            rel_name = step["filename"]
            target = output_dir / rel_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step.get("content", ""), encoding="utf-8")
            print(f"[{idx}/{len(steps)}] create_file  {rel_name}")
            open_line, open_col = _resolve_open_position(step)
            _open_file_in_vscode(target, line=open_line, column=open_col)
            _wait_for_editor(workspace_dir, target.name)
            time.sleep(2.0)  # Let VS Code settle after confirmed open
            _apply_step_highlights(workspace_dir, step)
            time.sleep(1.5)  # Wait for extension to render highlights
            _apply_step_highlights(workspace_dir, step)  # Re-trigger file watcher
            time.sleep(0.5)
        elif action == "run_command":
            command = step.get("command", "")
            print(f"[{idx}/{len(steps)}] run_command   {command}")
            subprocess.run(
                command,
                shell=True,
                cwd=workspace_dir,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.8)
        elif action == "pause":
            secs = int(step.get("seconds", 2))
            print(f"[{idx}/{len(steps)}] pause         {secs}s")
            for _ in range(secs):
                _check_abort()
                time.sleep(1)
        else:
            print(f"[{idx}/{len(steps)}] unknown action '{action}', skipping")

        if post_step_hook:
            post_step_hook(step, idx, len(steps))

    _clear_highlights(workspace_dir)
    print("\nDemo playback complete!")


def _save_primary_desktop_screenshot(target_file: Path) -> None:
    import pyautogui

    target_file.parent.mkdir(parents=True, exist_ok=True)
    image = pyautogui.screenshot()
    image.save(target_file)


def _count_create_file_steps(plan: Dict) -> int:
    return sum(1 for step in plan.get("steps", []) if step.get("action") == "create_file")


def _step_screenshot_targets(step: dict) -> list[dict]:
    """Return screenshot targets for a create_file step.

    If the step defines multiple line-based highlights, each highlight gets its own
    screenshot so off-screen ranges are captured deterministically.
    """
    highlights = step.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        return [{"open_line": None, "highlight": None, "suffix": ""}]

    targets: list[dict] = []
    for idx, entry in enumerate(highlights, 1):
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
        if start <= 0 or end < start:
            continue

        targets.append(
            {
                "open_line": start,
                "highlight": entry,
                "suffix": f"_h{idx:02d}_l{start}-{end}",
            }
        )

    if targets:
        return targets

    # Fallback to one screenshot when highlights are present but not line-based.
    return [{"open_line": None, "highlight": None, "suffix": ""}]


def _count_screenshot_targets(plan: Dict) -> int:
    total = 0
    for step in plan.get("steps", []):
        if step.get("action") != "create_file":
            continue
        total += len(_step_screenshot_targets(step))
    return total


def _build_screenshot_post_step_hook(
    plan: Dict,
    captures_dir: Path,
    workspace_dir: Path,
    title_hint: str,
) -> Callable[[dict, int, int], None]:
    screenshot_total = _count_screenshot_targets(plan)
    screenshot_index = 0

    def _post_step_hook(step: dict, idx: int, total: int) -> None:
        nonlocal screenshot_index
        if step.get("action") != "create_file":
            return

        filename = _sanitize_for_filename(step.get("filename", f"step-{idx}"))
        target_name = Path(step.get("filename", "")).name or filename
        step_targets = _step_screenshot_targets(step)
        target_file = workspace_dir / "output" / step.get("filename", "")

        for target in step_targets:
            if target.get("open_line"):
                _open_file_in_vscode(target_file, line=int(target["open_line"]), column=1)
                _wait_for_editor(workspace_dir, target_name)
                time.sleep(0.4)

            if target.get("highlight") is None:
                # No line-based highlight target; apply full step highlights.
                highlight_step = step
            else:
                # Focus one range at a time to guarantee off-screen sections are captured.
                highlight_step = {
                    "action": step.get("action"),
                    "highlights": [target["highlight"]],
                }

            apply_started = time.time()
            _apply_step_highlights(workspace_dir, highlight_step)
            if not _wait_for_highlight_apply(workspace_dir, target_name, apply_started):
                apply_started = time.time()
                _apply_step_highlights(workspace_dir, highlight_step)
                if not _wait_for_highlight_apply(workspace_dir, target_name, apply_started):
                    raise RuntimeError(
                        f"Highlight rendering could not be confirmed for {target_name}; capture aborted."
                    )

            screenshot_index += 1
            suffix = target.get("suffix", "")
            screenshot_file = captures_dir / f"{screenshot_index:02d}_{filename}{suffix}.png"

            _activate_vscode_window(title_hint)
            time.sleep(0.2)
            _save_primary_desktop_screenshot(screenshot_file)

            print(
                f"      screenshot {screenshot_index}/{screenshot_total}: "
                f"{screenshot_file.name}"
            )

    return _post_step_hook


def run_screenshot_play(
    plan: Dict,
    speed: float,
    countdown: int,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    session_dir: Path | None = None,
    artifact_dir: Path | None = None,
    screenshots_dir: str | None = None,
    plan_file_name: str | None = None,
    scenario_name: str | None = None,
) -> Tuple[Path, Path]:
    _enable_dpi_awareness()

    root = Path.cwd()
    if session_dir is None:
        session_dir = _create_session_dir(root)
    else:
        session_dir.mkdir(parents=True, exist_ok=True)

    if artifact_dir is None:
        artifact_dir = session_dir / (scenario_name or "play")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    effective_plan, skipped_run_commands = _visual_only_plan(plan)
    save_plan(effective_plan, artifact_dir / (plan_file_name or "plan.json"))
    if skipped_run_commands:
        print(
            f"Visual capture mode: skipped {skipped_run_commands} run_command step(s)."
        )

    workspace_dir = _prepare_demo_workspace(session_dir)
    captures_dir = Path(screenshots_dir) if screenshots_dir else artifact_dir / "screenshots"
    captures_dir.mkdir(parents=True, exist_ok=True)

    title_hint = f"{workspace_dir.name} - Visual Studio Code"
    post_step_hook = _build_screenshot_post_step_hook(
        plan=effective_plan,
        captures_dir=captures_dir,
        workspace_dir=workspace_dir,
        title_hint=title_hint,
    )

    try:
        _launch_vscode_window(workspace_dir)
        time.sleep(5.0)
        _activate_vscode_window(title_hint)
        _position_vscode_on_primary(title_hint)
        time.sleep(0.5)
        if clean_view:
            _prepare_clean_view_shortcuts()

        previous_cwd = Path.cwd()
        focus_stop = threading.Event()
        focus_thread = None
        if focus_lock:
            focus_thread = threading.Thread(
                target=_focus_keeper,
                args=(focus_stop, title_hint),
                daemon=True,
            )
            focus_thread.start()

        try:
            os.chdir(workspace_dir)
            if mode == "typing":
                play_demo(
                    effective_plan,
                    char_delay=speed,
                    countdown=countdown,
                    pre_step_hook=(lambda: _activate_vscode_window(title_hint)),
                    post_step_hook=post_step_hook,
                )
            else:
                _run_plan_stable_with_hook(
                    effective_plan,
                    workspace_dir,
                    title_hint,
                    post_step_hook=post_step_hook,
                )
        finally:
            focus_stop.set()
            if focus_thread is not None:
                focus_thread.join(timeout=1)
            os.chdir(previous_cwd)
    finally:
        _close_vscode_window(title_hint)

    return workspace_dir, captures_dir


def _stop_recording(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    try:
        if proc.stdin:
            proc.stdin.write(b"q\n")
            proc.stdin.flush()
    except Exception:
        proc.terminate()
    finally:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def run_recorded_play(
    plan: Dict,
    speed: float,
    countdown: int,
    video_format: str,
    resolution: str,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    session_dir: Path | None = None,
    artifact_dir: Path | None = None,
    video_file: str | None = None,
    capture_screenshots: bool = False,
    screenshots_dir: str | None = None,
    plan_file_name: str | None = None,
    scenario_name: str | None = None,
) -> Tuple[Path, Path, Path | None]:
    _enable_dpi_awareness()

    root = Path.cwd()
    if session_dir is None:
        session_dir = _create_session_dir(root)
    else:
        session_dir.mkdir(parents=True, exist_ok=True)

    if artifact_dir is None:
        artifact_dir = session_dir / (scenario_name or "play")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    effective_plan, skipped_run_commands = _visual_only_plan(plan)
    save_plan(effective_plan, artifact_dir / (plan_file_name or "plan.json"))
    if skipped_run_commands:
        print(
            f"Visual capture mode: skipped {skipped_run_commands} run_command step(s)."
        )

    workspace_dir = _prepare_demo_workspace(session_dir)

    suffix = ".mp4" if video_format == "mp4" else ".webm"
    recording_file = Path(video_file) if video_file else artifact_dir / f"playback-{_timestamp()}{suffix}"
    ffmpeg_log_file = artifact_dir / "ffmpeg.log"
    captures_dir: Path | None = None

    title_hint = f"{workspace_dir.name} - Visual Studio Code"
    post_step_hook: Callable[[dict, int, int], None] | None = None
    if capture_screenshots:
        captures_dir = Path(screenshots_dir) if screenshots_dir else artifact_dir / "screenshots"
        captures_dir.mkdir(parents=True, exist_ok=True)
        post_step_hook = _build_screenshot_post_step_hook(
            plan=effective_plan,
            captures_dir=captures_dir,
            workspace_dir=workspace_dir,
            title_hint=title_hint,
        )

    try:
        _launch_vscode_window(workspace_dir)
        time.sleep(5.0)
        _activate_vscode_window(title_hint)
        _position_vscode_on_primary(title_hint)
        time.sleep(0.5)
        if clean_view:
            _prepare_clean_view_shortcuts()

        rec_proc = _start_recording(
            recording_file,
            resolution=resolution,
            ffmpeg_log_file=ffmpeg_log_file,
        )
        previous_cwd = Path.cwd()
        focus_stop = threading.Event()
        focus_thread = None
        if focus_lock:
            focus_thread = threading.Thread(
                target=_focus_keeper,
                args=(focus_stop, title_hint),
                daemon=True,
            )
            focus_thread.start()
        try:
            os.chdir(workspace_dir)
            if mode == "typing":
                play_demo(
                    effective_plan,
                    char_delay=speed,
                    countdown=countdown,
                    pre_step_hook=(lambda: _activate_vscode_window(title_hint)),
                    post_step_hook=post_step_hook,
                )
            else:
                if post_step_hook:
                    _run_plan_stable_with_hook(
                        effective_plan,
                        workspace_dir,
                        title_hint,
                        post_step_hook=post_step_hook,
                    )
                else:
                    _run_plan_stable(effective_plan, workspace_dir, title_hint)
        finally:
            focus_stop.set()
            if focus_thread is not None:
                focus_thread.join(timeout=1)
            _stop_recording(rec_proc)
            os.chdir(previous_cwd)
    finally:
        _close_vscode_window(title_hint)

    if not recording_file.exists() or recording_file.stat().st_size == 0:
        raise RuntimeError(
            f"Recording file was not created correctly: {recording_file}. "
            f"Check ffmpeg log: {ffmpeg_log_file}"
        )

    return workspace_dir, recording_file, captures_dir


def generate_and_record(
    scenario: str,
    prompt: str,
    speed: float,
    countdown: int,
    video_format: str,
    resolution: str,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    plan_path: str | None = None,
    video_file: str | None = None,
) -> Tuple[Path, Path, Path]:
    plan = build_plan_for_scenario(scenario, prompt)

    root = Path.cwd()
    session_dir = _create_session_dir(root)
    scenario_dir = session_dir / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)

    trace_plan_file = scenario_dir / _default_plan_name(scenario)
    plan_file = Path(plan_path) if plan_path else trace_plan_file
    save_plan(plan, plan_file)
    if plan_file != trace_plan_file:
        save_plan(plan, trace_plan_file)

    workspace_dir, recording_file, _captures_dir = run_recorded_play(
        plan=plan,
        speed=speed,
        countdown=countdown,
        video_format=video_format,
        resolution=resolution,
        mode=mode,
        clean_view=clean_view,
        focus_lock=focus_lock,
        session_dir=session_dir,
        artifact_dir=scenario_dir,
        video_file=video_file,
    )
    return plan_file, workspace_dir, recording_file


def run_capture_play(
    plan: Dict,
    capture_mode: str,
    speed: float,
    countdown: int,
    video_format: str,
    resolution: str,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    session_dir: Path | None = None,
    artifact_dir: Path | None = None,
    video_file: str | None = None,
    screenshots_dir: str | None = None,
    plan_file_name: str | None = None,
    scenario_name: str | None = None,
) -> Tuple[Path, Path | None, Path | None]:
    # Keep capture behavior deterministic by output type:
    # - screenshots: stable mode (full file write + highlight render)
    # - mp4/both: typing mode (dynamic visual recording)
    if capture_mode == "screenshots":
        mode = "stable"
    elif capture_mode in {"mp4", "both"}:
        mode = "typing"

    if capture_mode == "screenshots":
        workspace_dir, captures_dir = run_screenshot_play(
            plan=plan,
            speed=speed,
            countdown=countdown,
            mode=mode,
            clean_view=clean_view,
            focus_lock=focus_lock,
            session_dir=session_dir,
            artifact_dir=artifact_dir,
            screenshots_dir=screenshots_dir,
            plan_file_name=plan_file_name,
            scenario_name=scenario_name,
        )
        return workspace_dir, None, captures_dir

    workspace_dir, recording_file, captures_dir = run_recorded_play(
        plan=plan,
        speed=speed,
        countdown=countdown,
        video_format=video_format,
        resolution=resolution,
        mode=mode,
        clean_view=clean_view,
        focus_lock=focus_lock,
        session_dir=session_dir,
        artifact_dir=artifact_dir,
        video_file=video_file,
        capture_screenshots=(capture_mode == "both"),
        screenshots_dir=screenshots_dir,
        plan_file_name=plan_file_name,
        scenario_name=scenario_name,
    )
    return workspace_dir, recording_file, captures_dir


def generate_and_capture(
    scenario: str,
    prompt: str,
    capture_mode: str,
    speed: float,
    countdown: int,
    video_format: str,
    resolution: str,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    plan_path: str | None = None,
    video_file: str | None = None,
    screenshots_dir: str | None = None,
) -> Tuple[Path, Path, Path | None, Path | None]:
    plan = build_plan_for_scenario(scenario, prompt)

    root = Path.cwd()
    session_dir = _create_session_dir(root)
    scenario_dir = session_dir / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)

    trace_plan_file = scenario_dir / _default_plan_name(scenario)
    plan_file = Path(plan_path) if plan_path else trace_plan_file
    save_plan(plan, plan_file)
    if plan_file != trace_plan_file:
        save_plan(plan, trace_plan_file)

    workspace_dir, recording_file, captures_dir = run_capture_play(
        plan=plan,
        capture_mode=capture_mode,
        speed=speed,
        countdown=countdown,
        video_format=video_format,
        resolution=resolution,
        mode=mode,
        clean_view=clean_view,
        focus_lock=focus_lock,
        session_dir=session_dir,
        artifact_dir=scenario_dir,
        video_file=video_file,
        screenshots_dir=screenshots_dir,
    )
    return plan_file, workspace_dir, recording_file, captures_dir


def generate_and_screenshot(
    scenario: str,
    prompt: str,
    speed: float,
    countdown: int,
    mode: str,
    clean_view: bool = False,
    focus_lock: bool = True,
    plan_path: str | None = None,
    screenshots_dir: str | None = None,
) -> Tuple[Path, Path, Path]:
    plan = build_plan_for_scenario(scenario, prompt)

    root = Path.cwd()
    session_dir = _create_session_dir(root)
    scenario_dir = session_dir / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)

    trace_plan_file = scenario_dir / _default_plan_name(scenario)
    plan_file = Path(plan_path) if plan_path else trace_plan_file
    save_plan(plan, plan_file)
    if plan_file != trace_plan_file:
        save_plan(plan, trace_plan_file)

    workspace_dir, captures_dir = run_screenshot_play(
        plan=plan,
        speed=speed,
        countdown=countdown,
        mode=mode,
        clean_view=clean_view,
        focus_lock=focus_lock,
        session_dir=session_dir,
        artifact_dir=scenario_dir,
        screenshots_dir=screenshots_dir,
    )
    return plan_file, workspace_dir, captures_dir
