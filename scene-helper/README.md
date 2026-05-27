# scene-helper

A CLI agent that turns short scene descriptions into video clips.

It uses an LLM (OpenAI) to expand casual descriptions into detailed cinematic prompts, then sends them to Runway ML for video generation.

## Setup

1. Install dependencies:

```bash
pip install -e .
```

2. Configure API keys by copying `.env.example` to `.env`.

## Usage

```bash
scene-helper "a cat sitting on a windowsill at sunset"
scene-helper --no-expand "Slow dolly shot of a tabby cat on a windowsill"
scene-helper --model gen4.5 --ratio 1280:720 --duration 8 "a spaceship launching"
```
