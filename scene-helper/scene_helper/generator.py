import os
import time
from pathlib import Path

import httpx
from runwayml import RunwayML

from .config import (
    DEFAULT_DURATION,
    DEFAULT_MODEL,
    DEFAULT_RATIO,
    OUTPUT_DIR,
    POLL_INTERVAL,
    RUNWAYML_API_SECRET,
)


def generate_video(
    prompt: str,
    model: str = DEFAULT_MODEL,
    ratio: str = DEFAULT_RATIO,
    duration: int = DEFAULT_DURATION,
) -> str:
    client = RunwayML(api_key=RUNWAYML_API_SECRET)

    print(f"  Model:    {model}")
    print(f"  Ratio:    {ratio}")
    print(f"  Duration: {duration}s")
    print()

    task = client.text_to_video.create(
        model=model,
        prompt_text=prompt,
        ratio=ratio,
        duration=duration,
    )

    task_id = task.id
    print(f"Task created: {task_id}")
    print("Waiting for video generation", end="", flush=True)

    while True:
        time.sleep(POLL_INTERVAL)
        status = client.tasks.retrieve(task_id)
        print(".", end="", flush=True)

        if status.status == "SUCCEEDED":
            print(" done!")
            break
        if status.status == "FAILED":
            raise RuntimeError(f"Video generation failed: {status.failure}")
        if status.status == "CANCELLED":
            raise RuntimeError("Video generation was cancelled.")

    video_url = status.output[0]
    return _download(video_url, task_id)


def _download(url: str, task_id: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = str(Path(OUTPUT_DIR) / f"{task_id}.mp4")

    print(f"Downloading to {out_path} ...")
    with httpx.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=8192):
                f.write(chunk)

    print("Saved.")
    return out_path
