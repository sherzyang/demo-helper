import time
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import pyautogui

try:
    import ctypes
except ImportError:  # pragma: no cover
    ctypes = None

# Keep playback deterministic; ESC remains the abort mechanism.
pyautogui.FAILSAFE = False
# Minimal built-in pause; we handle timing ourselves.
pyautogui.PAUSE = 0.01

DEFAULT_CHAR_DELAY = 0.03   # seconds between characters
DEFAULT_LINE_DELAY = 0.30   # extra pause after each newline
DEFAULT_COUNTDOWN = 5        # seconds before playback starts

_quick_open_primed = False


def _is_escape_pressed() -> bool:
    if ctypes is None:
        return False
    # High-order bit indicates key is currently down.
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)


def _check_abort() -> None:
    if _is_escape_pressed():
        raise KeyboardInterrupt("Playback aborted by ESC key")


def _get_foreground_window_title() -> str:
    if ctypes is None:
        return ""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    title_buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title_buf, length + 1)
    return title_buf.value


def _wait_for_vscode_foreground(timeout_seconds: float = 2.0) -> bool:
    end = time.time() + timeout_seconds
    while time.time() < end:
        _check_abort()
        title = _get_foreground_window_title().lower()
        if "visual studio code" in title:
            return True
        time.sleep(0.05)
    return False


def _ensure_editor_caret() -> None:
    # Dismiss any lingering overlays and click into likely editor area.
    pyautogui.press("escape")
    time.sleep(0.08)
    width, height = pyautogui.size()
    pyautogui.click(int(width * 0.55), int(height * 0.35))
    time.sleep(0.12)
    _wait_for_vscode_foreground(timeout_seconds=1.2)


def _prime_quick_open_once() -> None:
    global _quick_open_primed
    if _quick_open_primed:
        return

    # Prime command routing so first-step Ctrl+P is reliable.
    pyautogui.press("escape")
    time.sleep(0.06)
    pyautogui.press("escape")
    time.sleep(0.06)
    pyautogui.hotkey("ctrl", "p")
    time.sleep(0.25)
    pyautogui.press("escape")
    time.sleep(0.08)
    _quick_open_primed = True


def play_demo(
    plan: dict,
    char_delay: float = DEFAULT_CHAR_DELAY,
    line_delay: float = DEFAULT_LINE_DELAY,
    countdown: int = DEFAULT_COUNTDOWN,
    pre_step_hook: Callable[[], None] | None = None,
    post_step_hook: Callable[[dict, int, int], None] | None = None,
) -> None:
    """Execute a demo plan by simulating typing in VS Code."""
    title = plan.get("title", "Untitled")
    steps = plan["steps"]

    print(f"\nDemo: {title}")
    print(f"Steps: {len(steps)}")
    print(f"\nSwitch to VS Code now!  Starting in {countdown} seconds...")
    print("(Press ESC to abort)\n")

    for i in range(countdown, 0, -1):
        _check_abort()
        print(f"  {i}...")
        time.sleep(1)
    print("  Go!\n")

    for idx, step in enumerate(steps, 1):
        _check_abort()
        if pre_step_hook:
            pre_step_hook()
        action = step["action"]
        if action == "create_file":
            print(f"[{idx}/{len(steps)}] create_file  {step['filename']}")
            _create_file(step["filename"], step["content"],
                         char_delay, line_delay)
        elif action == "run_command":
            print(f"[{idx}/{len(steps)}] run_command   {step['command']}")
            _run_command(step["command"], char_delay)
        elif action == "pause":
            secs = step.get("seconds", 2)
            print(f"[{idx}/{len(steps)}] pause         {secs}s")
            time.sleep(secs)
        else:
            print(f"[{idx}/{len(steps)}] unknown action '{action}', skipping")

        if post_step_hook:
            post_step_hook(step, idx, len(steps))

    print("\nDemo playback complete!")


# ── helpers ──────────────────────────────────────────────────────────


def _type_text(text: str, char_delay: float, line_delay: float) -> None:
    """Type *text* character-by-character into the focused VS Code editor."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        _check_abort()
        for ch in line:
            _check_abort()
            if ch == "\t":
                pyautogui.press("tab")
            else:
                pyautogui.write(ch, interval=0)
            time.sleep(char_delay)

        if i < len(lines) - 1:
            # Dismiss autocomplete before pressing Enter
            pyautogui.press("escape")
            time.sleep(0.05)
            pyautogui.press("enter")
            time.sleep(line_delay)
            # Remove any auto-indentation so we control whitespace
            pyautogui.press("home")
            time.sleep(0.02)
            pyautogui.hotkey("shift", "end")
            time.sleep(0.02)
            pyautogui.press("delete")
            time.sleep(0.02)


def _create_file(
    filename: str,
    content: str,
    char_delay: float,
    line_delay: float,
) -> None:
    """Create *filename* in VS Code: new file → auto-type content → save."""
    path = (Path.cwd() / "output" / filename).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

    # Ensure the demo window is active before creating/opening the file.
    width, height = pyautogui.size()
    pyautogui.click(int(width * 0.55), int(height * 0.35))
    time.sleep(0.15)
    _wait_for_vscode_foreground(timeout_seconds=1.2)

    # Open file using code CLI to avoid sending global editor shortcuts.
    code_path = shutil.which("code")
    if not code_path:
        raise RuntimeError("VS Code CLI 'code' was not found on PATH.")
    subprocess.run(
        [code_path, "-r", "-g", f"{path}:1"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.9)

    # If Quick Open is still active, close it and force focus back to editor.
    pyautogui.press("escape")
    time.sleep(0.15)
    _ensure_editor_caret()
    time.sleep(0.25)
    _wait_for_vscode_foreground(timeout_seconds=1.2)

    _type_text(content, char_delay, line_delay)
    pyautogui.hotkey("ctrl", "s")
    time.sleep(0.15)

    def _normalize_for_compare(text: str) -> str:
        # VS Code may normalize line endings or add a trailing newline.
        return text.replace("\r\n", "\n").rstrip("\n")

    # Autosave may not flush immediately; if it does not, retry typing once in-editor.
    for attempt in range(2):
        for _ in range(6):
            time.sleep(0.35)
            try:
                if _normalize_for_compare(path.read_text(encoding="utf-8")) == _normalize_for_compare(content):
                    return
            except OSError:
                pass

        if attempt == 0:
            # Keep behavior visible: refocus editor, clear file, and retype once.
            _ensure_editor_caret()
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.press("delete")
            time.sleep(0.12)
            _type_text(content, char_delay, line_delay)

    # Keep the run alive for recording reliability if VS Code post-processing changed text.
    path.write_text(content, encoding="utf-8")


def _run_command(command: str, char_delay: float) -> None:
    """Focus the integrated terminal and execute *command*."""
    # Prefer command palette route to avoid Ctrl-based global shortcut conflicts.
    pyautogui.press("f1")
    time.sleep(0.25)
    pyautogui.write("Terminal: Focus Terminal", interval=0.01)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    _type_text(command, char_delay, line_delay=0)
    pyautogui.press("enter")
    time.sleep(1.0)
