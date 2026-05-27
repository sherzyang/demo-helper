import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from .agent_experience import launch_agent_gui
except ModuleNotFoundError:  # pragma: no cover
    launch_agent_gui = None
from .csharp_planner import plan_csharp_demo
from .planner import normalize_plan_highlights, plan_demo
from .pipeline_planner import plan_pipeline_demo
from .player import play_demo
from .recording_runner import (
    generate_and_capture,
    generate_and_record,
    generate_and_screenshot,
    run_capture_play,
    run_recorded_play,
    run_screenshot_play,
    validate_capture_environment,
)
from .sql_planner import plan_sql_demo


DEFAULT_RESOLUTION = "1920x1280"
DEFAULT_CAPTURE_MODE = "screenshots"


def _prompt_choice(prompt: str, choices: list[str], default: str) -> str:
    options = "/".join(choices)
    while True:
        value = input(f"{prompt} [{options}] (default: {default}): ").strip().lower()
        if not value:
            return default
        if value in choices:
            return value
        print(f"Invalid choice: {value}")


def _prompt_yes_no(prompt: str, default_yes: bool = False) -> bool:
    default_text = "Y/n" if default_yes else "y/N"
    while True:
        value = input(f"{prompt} [{default_text}]: ").strip().lower()
        if not value:
            return default_yes
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print(f"Invalid choice: {value}")


def _save_plan_file(path: str, plan: dict) -> None:
    plan_path = Path(path)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)


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


def _default_plan_output_for_scenario(scenario: str) -> str:
    return str(
        Path("recordings")
        / f"session-{_timestamp()}"
        / scenario
        / _default_plan_name(scenario)
    )


def _print_operator_checklist(capture_mode: str) -> None:
    print("\nOperator checklist (manual, not auto-validated):")
    print("  1. Close all apps and notifications except this VS Code window.")
    print("  2. Do not use other apps, mouse, or keyboard during capture.")
    print(f"  3. Recommended resolution: {DEFAULT_RESOLUTION}.")
    if capture_mode in {"mp4", "both"}:
        print("  Warning: built-in MP4 output does not guarantee visible code highlights.")
        print("  If highlighted video is required, run a 3rd-party recorder in parallel.")
    print("")


def _confirm_operator_ready(skip_confirmation: bool) -> None:
    if skip_confirmation:
        return
    ready = _prompt_yes_no("Proceed with capture using this checklist", default_yes=False)
    if not ready:
        raise RuntimeError("Capture cancelled by user before preflight confirmation.")


def _run_machine_validation(capture_mode: str, resolution: str) -> None:
    require_highlight_extension = capture_mode in {"screenshots", "both"}
    report = validate_capture_environment(
        expected_resolution=resolution,
        require_highlight_extension=require_highlight_extension,
    )

    print("\nMachine validation checks:")
    for check in report["checks"]:
        state = "PASS" if check["passed"] else "FAIL"
        print(f"  [{state}] {check['name']}: {check['detail']}")
    print(f"  [INFO] Demo workspace theme target: {report['configured_theme']}")
    print(f"  [INFO] Demo workspace zoom target: {report['configured_zoom_level']} (about 110%)")

    if not report["all_passed"]:
        raise RuntimeError(
            "Machine validation failed. Fix the failed checks above and retry."
        )

    print("Machine validation passed.\n")


def _launch_builtin_wizard() -> None:
    print("Starting demo-helper native wizard...")
    print("This fallback works without agent extensions.")

    scenario_aliases = {
        "python": "python",
        "sql": "sql",
        "sql-visual": "sql-visual",
        "csharp": "csharp",
        "azdo": "azdo",
        "gha": "gha",
    }

    scenario = _prompt_choice(
        "Scenario",
        list(scenario_aliases.keys()),
        default="python",
    )

    prompt = input("Describe the demo you want to create: ").strip()
    if not prompt:
        raise RuntimeError("Prompt is required.")

    capture_mode = _prompt_choice(
        "Output type",
        ["screenshots", "mp4", "both"],
        default=DEFAULT_CAPTURE_MODE,
    )

    video_format = "mp4"
    if capture_mode in {"mp4", "both"}:
        video_format = _prompt_choice(
            "Video format",
            ["mp4", "webm"],
            default="mp4",
        )

    mode = _prompt_choice(
        "Playback mode",
        ["stable", "typing"],
        default="stable",
    )

    _print_operator_checklist(capture_mode)
    _run_machine_validation(capture_mode=capture_mode, resolution=DEFAULT_RESOLUTION)
    _confirm_operator_ready(skip_confirmation=False)

    plan_file, workspace_dir, recording_file, captures_dir = generate_and_capture(
        scenario=scenario_aliases[scenario],
        prompt=prompt,
        capture_mode=capture_mode,
        speed=0.03,
        countdown=8,
        video_format=video_format,
        resolution=DEFAULT_RESOLUTION,
        mode=mode,
        clean_view=False,
        focus_lock=True,
        plan_path=None,
        video_file=None,
        screenshots_dir=None,
    )

    print(f"Plan saved to: {plan_file}")
    print(f"Playback workspace: {workspace_dir}")
    if recording_file:
        print(f"Recording saved to: {recording_file}")
    if captures_dir:
        print(f"Screenshots saved to: {captures_dir}")


def main():
    parser = argparse.ArgumentParser(
        prog="demo-helper",
        description=(
            "Turn written descriptions into auto-typed VS Code demos "
            "for screen recording."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── plan ─────────────────────────────────────────────────────────
    plan_p = sub.add_parser(
        "plan", help="Generate a demo plan from a description",
    )
    plan_p.add_argument(
        "description", help="Written description of what to demo",
    )
    plan_p.add_argument(
        "-o", "--output",
        help=(
            "Output file for the plan "
            "(default: recordings/session-<timestamp>/python/plan.json)"
        ),
    )

    # ── sql-plan ─────────────────────────────────────────────────────
    sql_plan_p = sub.add_parser(
        "sql-plan", help="Generate a SQL demo plan from a description",
    )
    sql_plan_p.add_argument(
        "description", help="Written description of what SQL demo to create",
    )
    sql_plan_p.add_argument(
        "-o", "--output",
        help=(
            "Output file for the SQL plan "
            "(default: recordings/session-<timestamp>/sql/sqlplan.json)"
        ),
    )
    sql_plan_p.add_argument(
        "--visual-only",
        action="store_true",
        help="Generate a visual-only SQL plan (no run_command steps)",
    )

    # ── csharp-plan ──────────────────────────────────────────────────
    csharp_plan_p = sub.add_parser(
        "csharp-plan", help="Generate a C#/.NET demo plan from a description",
    )
    csharp_plan_p.add_argument(
        "description", help="Written description of what C# demo to create",
    )
    csharp_plan_p.add_argument(
        "-o", "--output",
        help=(
            "Output file for the C# plan "
            "(default: recordings/session-<timestamp>/csharp/csharpplan.json)"
        ),
    )

    # ── azdo-plan ────────────────────────────────────────────────────
    azdo_plan_p = sub.add_parser(
        "azdo-plan", help="Generate an Azure DevOps YAML pipeline demo plan",
    )
    azdo_plan_p.add_argument(
        "description", help="Written description of what Azure DevOps pipeline demo to create",
    )
    azdo_plan_p.add_argument(
        "-o", "--output",
        help=(
            "Output file for the Azure DevOps plan "
            "(default: recordings/session-<timestamp>/azdo/azdoplan.json)"
        ),
    )

    # ── gha-plan ─────────────────────────────────────────────────────
    gha_plan_p = sub.add_parser(
        "gha-plan", help="Generate a GitHub Actions YAML pipeline demo plan",
    )
    gha_plan_p.add_argument(
        "description", help="Written description of what GitHub Actions demo to create",
    )
    gha_plan_p.add_argument(
        "-o", "--output",
        help=(
            "Output file for the GitHub Actions plan "
            "(default: recordings/session-<timestamp>/gha/ghaplan.json)"
        ),
    )

    # ── play ─────────────────────────────────────────────────────────
    play_p = sub.add_parser(
        "play", help="Play a previously saved demo plan in VS Code",
    )
    play_p.add_argument(
        "plan_file", help="Path to a plan JSON file",
    )
    play_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    play_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )

    # ── run ──────────────────────────────────────────────────────────
    run_p = sub.add_parser(
        "run", help="Plan and immediately play a demo",
    )
    run_p.add_argument(
        "description", help="Written description of what to demo",
    )
    run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    run_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )
    run_p.add_argument(
        "--save-plan",
        help="Also save the generated plan to this file",
    )

    # ── sql-run ──────────────────────────────────────────────────────
    sql_run_p = sub.add_parser(
        "sql-run", help="Create and immediately play a SQL demo",
    )
    sql_run_p.add_argument(
        "description", help="Written description of what SQL demo to create",
    )
    sql_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    sql_run_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )
    sql_run_p.add_argument(
        "--save-plan",
        help="Also save generated SQL plan to this file",
    )
    sql_run_p.add_argument(
        "--visual-only",
        action="store_true",
        help="Generate a visual-only SQL plan (no run_command steps)",
    )

    # ── csharp-run ───────────────────────────────────────────────────
    csharp_run_p = sub.add_parser(
        "csharp-run", help="Create and immediately play a C#/.NET demo",
    )
    csharp_run_p.add_argument(
        "description", help="Written description of what C# demo to create",
    )
    csharp_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    csharp_run_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )
    csharp_run_p.add_argument(
        "--save-plan",
        help="Also save generated C# plan to this file",
    )

    # ── azdo-run ─────────────────────────────────────────────────────
    azdo_run_p = sub.add_parser(
        "azdo-run", help="Create and immediately play an Azure DevOps YAML demo",
    )
    azdo_run_p.add_argument(
        "description", help="Written description of what Azure DevOps pipeline demo to create",
    )
    azdo_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    azdo_run_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )
    azdo_run_p.add_argument(
        "--save-plan",
        help="Also save generated Azure DevOps plan to this file",
    )

    # ── gha-run ──────────────────────────────────────────────────────
    gha_run_p = sub.add_parser(
        "gha-run", help="Create and immediately play a GitHub Actions YAML demo",
    )
    gha_run_p.add_argument(
        "description", help="Written description of what GitHub Actions demo to create",
    )
    gha_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    gha_run_p.add_argument(
        "--countdown", type=int, default=5,
        help="Seconds before playback starts (default: 5)",
    )
    gha_run_p.add_argument(
        "--save-plan",
        help="Also save generated GitHub Actions plan to this file",
    )

    # ── agent-ui ─────────────────────────────────────────────────────
    sub.add_parser(
        "agent-ui",
        help="Launch interactive agent GUI for scenario selection, planning, playback, and recording",
    )

    # ── record-play ──────────────────────────────────────────────────
    record_play_p = sub.add_parser(
        "record-play",
        help="Open clean VS Code window, play a plan, and record playback to webm/mp4",
    )
    record_play_p.add_argument("plan_file", help="Path to an existing plan JSON file")
    record_play_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    record_play_p.add_argument(
        "--countdown", type=int, default=8,
        help="Seconds before playback starts (default: 8)",
    )
    record_play_p.add_argument(
        "--capture", choices=["mp4", "screenshots", "both"], default=DEFAULT_CAPTURE_MODE,
        help="Capture output type (default: screenshots)",
    )
    record_play_p.add_argument(
        "--format", choices=["webm", "mp4"], default="mp4",
        help="Recording format (default: mp4)",
    )
    record_play_p.add_argument(
        "--resolution", default=DEFAULT_RESOLUTION,
        help="Output recording resolution WIDTHxHEIGHT (default: 1920x1280)",
    )
    record_play_p.add_argument(
        "--mode", choices=["stable", "typing"], default="typing",
        help="Playback mode for recording (default: typing)",
    )
    record_play_p.add_argument(
        "--clean-view",
        action="store_true",
        help="Use VS Code keyboard shortcuts to hide panes before recording (off by default)",
    )
    record_play_p.add_argument(
        "--no-focus-lock",
        action="store_true",
        help="Do not force VS Code to stay focused during recording",
    )
    record_play_p.add_argument(
        "--video-file",
        help="Optional custom output video file path",
    )
    record_play_p.add_argument(
        "--screenshots-dir",
        help="Optional custom output directory for screenshots",
    )
    record_play_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip checklist confirmation prompt",
    )

    # ── record-run ───────────────────────────────────────────────────
    record_run_p = sub.add_parser(
        "record-run",
        help="Generate plan, open clean VS Code window, play, and record in one command",
    )
    record_run_p.add_argument(
        "scenario",
        choices=["python", "sql", "sql-visual", "csharp", "azdo", "gha"],
        help="Scenario to generate and record",
    )
    record_run_p.add_argument("prompt", help="Prompt to generate the plan")
    record_run_p.add_argument(
        "--plan-file",
        help="Optional custom output plan path",
    )
    record_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    record_run_p.add_argument(
        "--countdown", type=int, default=8,
        help="Seconds before playback starts (default: 8)",
    )
    record_run_p.add_argument(
        "--capture", choices=["mp4", "screenshots", "both"], default=DEFAULT_CAPTURE_MODE,
        help="Capture output type (default: screenshots)",
    )
    record_run_p.add_argument(
        "--format", choices=["webm", "mp4"], default="mp4",
        help="Recording format (default: mp4)",
    )
    record_run_p.add_argument(
        "--resolution", default=DEFAULT_RESOLUTION,
        help="Output recording resolution WIDTHxHEIGHT (default: 1920x1280)",
    )
    record_run_p.add_argument(
        "--mode", choices=["stable", "typing"], default="typing",
        help="Playback mode for recording (default: typing)",
    )
    record_run_p.add_argument(
        "--clean-view",
        action="store_true",
        help="Use VS Code keyboard shortcuts to hide panes before recording (off by default)",
    )
    record_run_p.add_argument(
        "--no-focus-lock",
        action="store_true",
        help="Do not force VS Code to stay focused during recording",
    )
    record_run_p.add_argument(
        "--video-file",
        help="Optional custom output video file path",
    )
    record_run_p.add_argument(
        "--screenshots-dir",
        help="Optional custom output directory for screenshots",
    )
    record_run_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip checklist confirmation prompt",
    )

    # ── screenshot-play ──────────────────────────────────────────────
    screenshot_play_p = sub.add_parser(
        "screenshot-play",
        help="Open clean VS Code window, play a plan, and capture one screenshot per create_file step",
    )
    screenshot_play_p.add_argument("plan_file", help="Path to an existing plan JSON file")
    screenshot_play_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    screenshot_play_p.add_argument(
        "--countdown", type=int, default=8,
        help="Seconds before playback starts (default: 8)",
    )
    screenshot_play_p.add_argument(
        "--mode", choices=["stable", "typing"], default="stable",
        help="Playback mode for screenshot capture (default: stable)",
    )
    screenshot_play_p.add_argument(
        "--clean-view",
        action="store_true",
        help="Use VS Code keyboard shortcuts to hide panes before playback (off by default)",
    )
    screenshot_play_p.add_argument(
        "--no-focus-lock",
        action="store_true",
        help="Do not force VS Code to stay focused during playback",
    )
    screenshot_play_p.add_argument(
        "--screenshots-dir",
        help="Optional custom output directory for screenshots",
    )
    screenshot_play_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip checklist confirmation prompt",
    )

    # ── screenshot-run ───────────────────────────────────────────────
    screenshot_run_p = sub.add_parser(
        "screenshot-run",
        help="Generate plan, open clean VS Code window, play, and capture screenshots in one command",
    )
    screenshot_run_p.add_argument(
        "scenario",
        choices=["python", "sql", "sql-visual", "csharp", "azdo", "gha"],
        help="Scenario to generate and capture",
    )
    screenshot_run_p.add_argument("prompt", help="Prompt to generate the plan")
    screenshot_run_p.add_argument(
        "--plan-file",
        help="Optional custom output plan path",
    )
    screenshot_run_p.add_argument(
        "--speed", type=float, default=0.03,
        help="Seconds between characters (default: 0.03)",
    )
    screenshot_run_p.add_argument(
        "--countdown", type=int, default=8,
        help="Seconds before playback starts (default: 8)",
    )
    screenshot_run_p.add_argument(
        "--mode", choices=["stable", "typing"], default="stable",
        help="Playback mode for screenshot capture (default: stable)",
    )
    screenshot_run_p.add_argument(
        "--clean-view",
        action="store_true",
        help="Use VS Code keyboard shortcuts to hide panes before playback (off by default)",
    )
    screenshot_run_p.add_argument(
        "--no-focus-lock",
        action="store_true",
        help="Do not force VS Code to stay focused during playback",
    )
    screenshot_run_p.add_argument(
        "--screenshots-dir",
        help="Optional custom output directory for screenshots",
    )
    screenshot_run_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip checklist confirmation prompt",
    )

    args = parser.parse_args()

    if args.command == "plan":
        print(f'Planning demo for: "{args.description}"')
        plan = normalize_plan_highlights(plan_demo(args.description))
        output_path = args.output or _default_plan_output_for_scenario("python")
        _save_plan_file(output_path, plan)
        print(f"Plan saved to {output_path}")
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

    elif args.command == "sql-plan":
        print(f'Planning SQL demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_sql_demo(args.description, visual_only=args.visual_only)
        )
        scenario = "sql-visual" if args.visual_only else "sql"
        output_path = args.output or _default_plan_output_for_scenario(scenario)
        _save_plan_file(output_path, plan)
        print(f"SQL plan saved to {output_path}")
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

    elif args.command == "csharp-plan":
        print(f'Planning C# demo for: "{args.description}"')
        plan = normalize_plan_highlights(plan_csharp_demo(args.description))
        output_path = args.output or _default_plan_output_for_scenario("csharp")
        _save_plan_file(output_path, plan)
        print(f"C# plan saved to {output_path}")
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

    elif args.command == "azdo-plan":
        print(f'Planning Azure DevOps pipeline demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_pipeline_demo(args.description, pipeline_type="azure-devops")
        )
        output_path = args.output or _default_plan_output_for_scenario("azdo")
        _save_plan_file(output_path, plan)
        print(f"Azure DevOps plan saved to {output_path}")
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

    elif args.command == "gha-plan":
        print(f'Planning GitHub Actions demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_pipeline_demo(args.description, pipeline_type="github-actions")
        )
        output_path = args.output or _default_plan_output_for_scenario("gha")
        _save_plan_file(output_path, plan)
        print(f"GitHub Actions plan saved to {output_path}")
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

    elif args.command == "play":
        with open(args.plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "run":
        print(f'Planning demo for: "{args.description}"')
        plan = normalize_plan_highlights(plan_demo(args.description))
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

        if args.save_plan:
            _save_plan_file(args.save_plan, plan)
            print(f"Plan saved to {args.save_plan}")

        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "sql-run":
        print(f'Planning SQL demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_sql_demo(args.description, visual_only=args.visual_only)
        )
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

        if args.save_plan:
            _save_plan_file(args.save_plan, plan)
            print(f"SQL plan saved to {args.save_plan}")

        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "csharp-run":
        print(f'Planning C# demo for: "{args.description}"')
        plan = normalize_plan_highlights(plan_csharp_demo(args.description))
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

        if args.save_plan:
            _save_plan_file(args.save_plan, plan)
            print(f"C# plan saved to {args.save_plan}")

        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "azdo-run":
        print(f'Planning Azure DevOps pipeline demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_pipeline_demo(args.description, pipeline_type="azure-devops")
        )
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

        if args.save_plan:
            _save_plan_file(args.save_plan, plan)
            print(f"Azure DevOps plan saved to {args.save_plan}")

        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "gha-run":
        print(f'Planning GitHub Actions demo for: "{args.description}"')
        plan = normalize_plan_highlights(
            plan_pipeline_demo(args.description, pipeline_type="github-actions")
        )
        print(f"  Title: {plan.get('title', 'Untitled')}")
        print(f"  Steps: {len(plan['steps'])}")

        if args.save_plan:
            _save_plan_file(args.save_plan, plan)
            print(f"GitHub Actions plan saved to {args.save_plan}")

        play_demo(plan, char_delay=args.speed, countdown=args.countdown)

    elif args.command == "agent-ui":
        if launch_agent_gui is None:
            _launch_builtin_wizard()
        else:
            launch_agent_gui()

    elif args.command == "record-play":
        _run_machine_validation(capture_mode=args.capture, resolution=args.resolution)
        _print_operator_checklist(args.capture)
        _confirm_operator_ready(skip_confirmation=args.yes)

        effective_mode = "stable" if args.capture == "screenshots" else "typing"
        if args.mode != effective_mode:
            print(f"Capture mode '{args.capture}' forces playback mode '{effective_mode}'.")

        with open(args.plan_file, encoding="utf-8") as f:
            plan = normalize_plan_highlights(json.load(f))

        plan_path = Path(args.plan_file)
        scenario_name = plan_path.stem

        workspace_dir, recording_file, captures_dir = run_capture_play(
            plan=plan,
            capture_mode=args.capture,
            speed=args.speed,
            countdown=args.countdown,
            video_format=args.format,
            resolution=args.resolution,
            mode=effective_mode,
            clean_view=args.clean_view,
            focus_lock=not args.no_focus_lock,
            video_file=args.video_file,
            screenshots_dir=args.screenshots_dir,
            plan_file_name=plan_path.name,
            scenario_name=scenario_name,
        )
        print(f"Playback workspace: {workspace_dir}")
        if recording_file:
            print(f"Recording saved to: {recording_file}")
        if captures_dir:
            print(f"Screenshots saved to: {captures_dir}")

    elif args.command == "record-run":
        _run_machine_validation(capture_mode=args.capture, resolution=args.resolution)
        _print_operator_checklist(args.capture)
        _confirm_operator_ready(skip_confirmation=args.yes)

        effective_mode = "stable" if args.capture == "screenshots" else "typing"
        if args.mode != effective_mode:
            print(f"Capture mode '{args.capture}' forces playback mode '{effective_mode}'.")

        plan_file, workspace_dir, recording_file, captures_dir = generate_and_capture(
            scenario=args.scenario,
            prompt=args.prompt,
            capture_mode=args.capture,
            speed=args.speed,
            countdown=args.countdown,
            video_format=args.format,
            resolution=args.resolution,
            mode=effective_mode,
            clean_view=args.clean_view,
            focus_lock=not args.no_focus_lock,
            plan_path=args.plan_file,
            video_file=args.video_file,
            screenshots_dir=args.screenshots_dir,
        )
        print(f"Plan saved to: {plan_file}")
        print(f"Playback workspace: {workspace_dir}")
        if recording_file:
            print(f"Recording saved to: {recording_file}")
        if captures_dir:
            print(f"Screenshots saved to: {captures_dir}")

    elif args.command == "screenshot-play":
        _run_machine_validation(capture_mode="screenshots", resolution=DEFAULT_RESOLUTION)
        _print_operator_checklist("screenshots")
        _confirm_operator_ready(skip_confirmation=args.yes)

        if args.mode != "stable":
            print("Screenshot capture forces playback mode 'stable'.")

        with open(args.plan_file, encoding="utf-8") as f:
            plan = normalize_plan_highlights(json.load(f))

        plan_path = Path(args.plan_file)
        scenario_name = plan_path.stem

        workspace_dir, captures_dir = run_screenshot_play(
            plan=plan,
            speed=args.speed,
            countdown=args.countdown,
            mode="stable",
            clean_view=args.clean_view,
            focus_lock=not args.no_focus_lock,
            screenshots_dir=args.screenshots_dir,
            plan_file_name=plan_path.name,
            scenario_name=scenario_name,
        )
        print(f"Playback workspace: {workspace_dir}")
        print(f"Screenshots saved to: {captures_dir}")

    elif args.command == "screenshot-run":
        _run_machine_validation(capture_mode="screenshots", resolution=DEFAULT_RESOLUTION)
        _print_operator_checklist("screenshots")
        _confirm_operator_ready(skip_confirmation=args.yes)

        if args.mode != "stable":
            print("Screenshot capture forces playback mode 'stable'.")

        plan_file, workspace_dir, captures_dir = generate_and_screenshot(
            scenario=args.scenario,
            prompt=args.prompt,
            speed=args.speed,
            countdown=args.countdown,
            mode="stable",
            clean_view=args.clean_view,
            focus_lock=not args.no_focus_lock,
            plan_path=args.plan_file,
            screenshots_dir=args.screenshots_dir,
        )
        print(f"Plan saved to: {plan_file}")
        print(f"Playback workspace: {workspace_dir}")
        print(f"Screenshots saved to: {captures_dir}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        print("Playback cancelled by user.")
        sys.exit(130)
