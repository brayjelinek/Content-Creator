"""End-to-end gameplay clip generation pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from scripts.caption_generator import generate_captions
from scripts.clip_cutter import get_video_duration, process_highlights
from scripts.frame_extractor import extract_frames
from scripts.highlight_detector import detect_highlights
from scripts.vision_analyzer import VisionAnalyzer


def _user_data_dir() -> Path:
    app_dir_name = "GameplayAutoEditor"
    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")

    path = base / app_dir_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return _user_data_dir()
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _runtime_root()
BUNDLED_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


def run_pipeline(
    video_path: str | Path,
    config_path: str | Path | None = None,
    config_override: dict | None = None,
) -> dict:
    config = load_config(config_path)
    if config_override:
        config = _deep_merge(config, config_override)
    paths = ensure_project_dirs()
    input_video = resolve_video_path(video_path)

    video_stem = input_video.stem
    frame_dir = paths["processed"] / "frames" / video_stem
    report_dir = paths["processed"] / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    vision_config = config.get("vision", {})
    print(f"[1/5] Extracting frames from {input_video.name}...")
    frame_samples = extract_frames(
        input_video,
        frame_dir,
        interval_seconds=float(vision_config.get("analysis_interval_seconds", 3)),
        max_frames=int(vision_config.get("max_frames_to_analyze", 24)),
        jpeg_quality=int(vision_config.get("jpeg_quality", 85)),
    )
    if not frame_samples:
        raise RuntimeError("No frames were extracted. Check that the input is a valid video file.")

    print(f"[2/5] Analyzing {len(frame_samples)} frames with {vision_config.get('provider', 'heuristic')}...")
    analyzer = VisionAnalyzer(vision_config)
    analyses = analyzer.analyze_frames(frame_samples)
    _write_json(report_dir / f"{video_stem}_analysis.json", analyses)

    print("[3/5] Detecting highlight moments...")
    duration = get_video_duration(input_video)
    highlights = detect_highlights(analyses, duration, config.get("highlight_detection", {}))
    if not highlights:
        raise RuntimeError("No highlights could be detected from the sampled frames.")

    print("[4/5] Generating hooks and captions...")
    captioned_highlights = generate_captions(
        highlights,
        video_name=video_stem,
        add_hashtags=bool(config.get("rendering", {}).get("add_hashtags", True)),
    )
    _write_json(report_dir / f"{video_stem}_highlights.json", captioned_highlights)

    print("[5/5] Cutting and rendering vertical clips with FFmpeg...")
    rendered = process_highlights(
        input_video,
        captioned_highlights,
        paths["processed"],
        paths["final"],
        config.get("rendering", {}),
    )

    report = {
        "input_video": str(input_video),
        "duration_seconds": round(duration, 2),
        "frames_analyzed": len(frame_samples),
        "clips_created": len(rendered),
        "clips": rendered,
    }
    _write_json(report_dir / f"{video_stem}_run_report.json", report)
    return report


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    load_dotenv(PROJECT_ROOT / ".env")
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.json"
    if not path.exists() and not config_path:
        bundled_config = BUNDLED_ROOT / "config.json"
        if bundled_config.exists():
            path = bundled_config
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    return _apply_env_overrides(config)


def ensure_project_dirs() -> dict[str, Path]:
    paths = {
        "raw": PROJECT_ROOT / "raw_clips",
        "processed": PROJECT_ROOT / "processed_clips",
        "final": PROJECT_ROOT / "final_clips",
        "models": PROJECT_ROOT / "models",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def resolve_video_path(video_path: str | Path) -> Path:
    candidate = Path(video_path)
    if candidate.exists():
        return candidate.resolve()

    project_relative = PROJECT_ROOT / candidate
    if project_relative.exists():
        return project_relative.resolve()

    raw_relative = PROJECT_ROOT / "raw_clips" / candidate.name
    if raw_relative.exists():
        return raw_relative.resolve()

    raise FileNotFoundError(
        f"Could not find video '{video_path}'. Put it in {PROJECT_ROOT / 'raw_clips'} "
        "or pass an absolute path."
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(config)
    vision = dict(config.get("vision", {}))

    env_map = {
        "VISION_PROVIDER": "provider",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "ANTHROPIC_MODEL": "anthropic_model",
    }
    for env_name, config_name in env_map.items():
        value = os.getenv(env_name)
        if value:
            vision[config_name] = value

    config["vision"] = vision
    return config


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-powered gameplay clip generator")
    parser.add_argument("video", help="Path to a raw gameplay video, e.g. raw_clips/myvideo.mp4")
    parser.add_argument("--config", help="Optional path to config.json", default=None)
    args = parser.parse_args()

    report = run_pipeline(args.video, args.config)
    print("\nDone. Final clips:")
    for clip in report["clips"]:
        print(f"- {clip['final_clip']} (score {clip['score']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
