# Gameplay Auto Editor

A minimal AI-powered gameplay clip generator. It samples raw gameplay videos, scores highlight moments with a vision model or local heuristic fallback, cuts clips with FFmpeg, converts them to vertical 1080x1920, adds hook/caption overlays, and writes final clips to `final_clips/`.

## Project structure

```text
gameplay-auto-editor/
  raw_clips/
  processed_clips/
  final_clips/
  models/
  scripts/
    frame_extractor.py
    vision_analyzer.py
    highlight_detector.py
    clip_cutter.py
    caption_generator.py
    pipeline.py
  config.json
  run.py
  requirements.txt
  README.md
```

## Requirements

- Python 3.10+
- FFmpeg and FFprobe installed and available on `PATH`
- Optional: OpenAI or Anthropic API key for real vision analysis

Install Python dependencies:

```bash
cd gameplay-auto-editor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Check FFmpeg:

```bash
ffmpeg -version
ffprobe -version
```

## Configuration

Edit `config.json`.

For a fully local starter run, keep:

```json
"provider": "heuristic"
```

For OpenAI vision analysis:

```json
{
  "vision": {
    "provider": "openai",
    "openai_api_key": "YOUR_KEY",
    "openai_model": "gpt-4o-mini"
  }
}
```

You can also leave `openai_api_key` blank and set:

```bash
export OPENAI_API_KEY="YOUR_KEY"
```

For Anthropic vision analysis:

```json
{
  "vision": {
    "provider": "anthropic",
    "anthropic_api_key": "YOUR_KEY",
    "anthropic_model": "claude-3-5-haiku-latest"
  }
}
```

Or use:

```bash
export ANTHROPIC_API_KEY="YOUR_KEY"
```

Set `"provider": "auto"` to use OpenAI if `OPENAI_API_KEY` exists, Anthropic if `ANTHROPIC_API_KEY` exists, or the local heuristic if neither exists.

## Run

Put gameplay videos in `raw_clips/`, then run:

```bash
python run.py raw_clips/myvideo.mp4
```

Outputs:

- Extracted frames: `processed_clips/frames/<video_name>/`
- JSON reports: `processed_clips/reports/`
- Raw cut clips: `processed_clips/`
- Final vertical clips: `final_clips/`

## How the pipeline works

1. `frame_extractor.py` samples frames with OpenCV and calculates motion, brightness, and sharpness signals.
2. `vision_analyzer.py` sends frames to OpenAI/Anthropic when configured, or uses the local heuristic fallback.
3. `highlight_detector.py` scores and merges nearby high-value moments into clip ranges.
4. `caption_generator.py` creates short hook text and captions.
5. `clip_cutter.py` uses FFmpeg to cut segments, crop/scale to 1080x1920, and overlay text.
6. `pipeline.py` ties all steps together.

## Notes

- The heuristic mode is useful for testing the full workflow without API usage.
- API vision analysis quality depends on sampled frames. Increase `max_frames_to_analyze` or reduce `analysis_interval_seconds` for denser analysis.
- FFmpeg `drawtext` support is required for text overlays. Most standard FFmpeg builds include it.
