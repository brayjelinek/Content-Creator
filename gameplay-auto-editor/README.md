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
  dashboard.py
  desktop_app.py
  build_desktop_app.py
  install_desktop_launcher.py
  Launch Gameplay Auto Editor.bat
  Launch Gameplay Auto Editor.command
  launch_desktop_app.sh
  launch_dashboard.sh
  NON_TECHNICAL_SETUP.md
  PACKAGING.md
  run.py
  requirements.txt
  requirements-build.txt
  README.md
```

## Requirements

- Python 3.10+
- FFmpeg and FFprobe installed and available on `PATH`
- Optional: OpenAI or Anthropic API key for real vision analysis

Install Python dependencies:

```bash
cd gameplay-auto-editor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Check FFmpeg:

```bash
ffmpeg -version
ffprobe -version
```

## Configuration

Edit `config.json`, set environment variables, or copy `.env.example` to `.env`.

```bash
cp .env.example .env
```

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

## Run as a desktop app

The easiest non-technical way to use the tool is the native desktop app window.

### Best option: download a packaged app build

For a true app-like experience, use the GitHub Actions artifact for your operating system:

1. Run or open the **Build desktop app** workflow.
2. Download the artifact for Windows, macOS, or Linux.
3. Unzip it.
4. Open **Gameplay Auto Editor** from the unzipped app folder.
5. Move the app or launcher to your Desktop if you want a desktop icon.

This is the recommended non-technical testing path.

### Source-folder launchers

If you are running from the source project folder instead of a packaged artifact:

Double-click the launcher for your computer:

- Windows: `Launch Gameplay Auto Editor.bat`
- Mac: `Launch Gameplay Auto Editor.command`
- Linux: `launch_desktop_app.sh`

The app window lets you:

1. Choose a gameplay video.
2. Paste/save your OpenAI API key if needed.
3. Choose how many sample clips to generate.
4. Choose how many AI frames to analyze.
5. Generate clips.
6. Review each clip's score, hook, and caption.
7. Play, open, export, or copy captions for clips you like.

OpenAI analysis sends sampled frames to the API. For first tests, use **Max AI frames = 5-10**. More frames can improve scouting, but it may take several minutes because each frame is analyzed by the vision model.

For a quick workflow test, set **Vision mode = heuristic**. That skips paid API calls and should be much faster.

### Create a desktop icon

Important: if this is running in Cursor Cloud, the desktop icon is created on the remote cloud computer, not on your personal computer. To get an icon on your own desktop, download this project to your computer and run the launcher installer there.

Create a desktop icon once:

```bash
python3 install_desktop_launcher.py
```

Then double-click **Gameplay Auto Editor** on your desktop.

The launcher will create a local Python environment and install dependencies the first time it runs.

For plain-English setup help, see `NON_TECHNICAL_SETUP.md`.

### Build a packaged app

To package the app as a normal desktop executable:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
python build_desktop_app.py
```

The built app appears in `dist/Gameplay Auto Editor/`.

See `PACKAGING.md` for GitHub Actions builds and platform-specific notes.

## Run with the browser dashboard

The browser dashboard is still available as an alternate interface.

Run:

```bash
./launch_dashboard.sh
```

Or use the direct command:

```bash
streamlit run dashboard.py
```

Then:

1. Open the local URL shown in the terminal.
2. Drop or upload a gameplay video.
3. Choose the number of sample clips to generate.
4. Click **Generate sample clips**.
5. Review each vertical clip in the browser.
6. Download the clips you want to post.

## Run

Put gameplay videos in `raw_clips/`, then run:

```bash
python3 run.py raw_clips/myvideo.mp4
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
7. `dashboard.py` provides the upload, preview, and download UI.

## Notes

- The heuristic mode is useful for testing the full workflow without API usage.
- API vision analysis quality depends on sampled frames. Increase `max_frames_to_analyze` or reduce `analysis_interval_seconds` for denser analysis.
- FFmpeg `drawtext` support is required for text overlays. Most standard FFmpeg builds include it.
