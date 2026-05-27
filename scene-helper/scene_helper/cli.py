import argparse
import sys

from .config import DEFAULT_DURATION, DEFAULT_MODEL, DEFAULT_RATIO
from .expander import expand_scene
from .generator import generate_video


def main():
    parser = argparse.ArgumentParser(
        prog="scene-helper",
        description="Turn short scene descriptions into video clips.",
    )
    parser.add_argument(
        "description",
        help="A short description of the scene",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Runway model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--ratio",
        default=DEFAULT_RATIO,
        help=f"Output aspect ratio (default: {DEFAULT_RATIO})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Video duration in seconds (default: {DEFAULT_DURATION})",
    )
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip LLM prompt expansion and use the description as-is",
    )

    args = parser.parse_args()

    if args.no_expand:
        prompt = args.description
        print(f"\nUsing prompt as-is:\n  {prompt}\n")
    else:
        print(f"\nExpanding scene: \"{args.description}\" ...")
        prompt = expand_scene(args.description)
        print(f"\nExpanded prompt:\n  {prompt}\n")

    print("Generating video...")
    try:
        path = generate_video(
            prompt=prompt,
            model=args.model,
            ratio=args.ratio,
            duration=args.duration,
        )
        print(f"\nVideo saved to: {path}")
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
