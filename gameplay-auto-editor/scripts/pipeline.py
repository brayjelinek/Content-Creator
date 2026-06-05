"""End-to-end gameplay clip generation pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from scripts.caption_generator import generate_captions
from scripts.clip_cutter import get_video_duration, process_highlights
from scripts.frame_extractor import extract_frames
from scripts.highlight_detector import detect_highlights
from scripts.logging_utils import setup_pipeline_logging
from scripts.vision_analyzer import VisionAnalyzer

logger = logging.getLogger(__name__)


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
    """Run the full clip generation workflow for one input video."""
    config = load_config(config_path)
    if config_override:
        config = _deep_merge(config, config_override)

    paths = ensure_project_dirs()
    input_video = resolve_video_path(video_path)
    video_stem = input_video.stem

    log_path = setup_pipeline_logging(paths["logs"], video_stem)
    logger.info("[Pipeline] Writing logs to %s", log_path)

    frame_dir = paths["processed"] / "frames" / video_stem
    report_dir = paths["processed"] / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    vision_config = config.get("vision", {})
    render_config = config.get("rendering", {})

    logger.info("[Pipeline] Extracting frames...")
    frame_samples = extract_frames(
        input_video,
        frame_dir,
        interval_seconds=float(vision_config.get("analysis_interval_seconds", 3)),
        max_frames=int(vision_config.get("max_frames_to_analyze", 24)),
        jpeg_quality=int(vision_config.get("jpeg_quality", 85)),
    )
    if not frame_samples:
        logger.error("[Pipeline] No frames extracted — check that the input is a valid video file.")
        raise RuntimeError("No frames were extracted. Check that the input is a valid video file.")
    logger.info("[Pipeline] Extracted %s frame sample(s) from %s", len(frame_samples), input_video.name)

    provider = vision_config.get("provider", "heuristic")
    if provider == "heuristic":
        logger.info("[Pipeline] Running heuristic analysis...")
    else:
        logger.info("[Pipeline] Running %s analysis on %s frame(s)...", provider, len(frame_samples))
    analyzer = VisionAnalyzer(vision_config)
    analyses = analyzer.analyze_frames(frame_samples)
    _write_json(report_dir / f"{video_stem}_analysis.json", analyses)

    duration = get_video_duration(input_video)
    logger.info("[Pipeline] Video duration: %.2fs", duration)
    highlights = detect_highlights(analyses, duration, config.get("highlight_detection", {}))
    logger.info("[Pipeline] Highlights detected: %s", len(highlights))

    if not highlights:
        logger.warning("[Pipeline] No highlights detected — stopping before render.")
        report = {
            "input_video": str(input_video),
            "duration_seconds": round(duration, 2),
            "frames_analyzed": len(frame_samples),
            "clips_created": 0,
            "clips": [],
            "log_file": str(log_path),
        }
        _write_json(report_dir / f"{video_stem}_run_report.json", report)
        logger.warning("[Pipeline] Final clips generated: 0")
        logger.warning("[Pipeline] No clips were generated — check logs above.")
        return report

    for highlight in highlights:
        logger.info(
            "[Pipeline] Highlight %s at %.2fs (score %.2f, %.2fs-%.2fs)",
            highlight.get("id"),
            float(highlight.get("timestamp", 0)),
            float(highlight.get("score", 0)),
            float(highlight.get("start", 0)),
            float(highlight.get("end", 0)),
        )

    logger.info("[Pipeline] Generating hooks and captions")
    captioned_highlights = generate_captions(
        highlights,
        video_name=video_stem,
        add_hashtags=bool(render_config.get("add_hashtags", True)),
        render_config=render_config,
    )
    _write_json(report_dir / f"{video_stem}_highlights.json", captioned_highlights)

    logger.info("[Pipeline] Starting clip rendering...")
    rendered = process_highlights(
        video_path=input_video,
        highlights=captioned_highlights,
        processed_dir=paths["processed"],
        final_dir=paths["final"],
        render_config=render_config,
        video_duration=duration,
    )
    for clip in rendered:
        logger.info(
            "[Pipeline] Final clip ready: %s (score %s)",
            clip["final_clip"],
            clip.get("score"),
        )

    logger.info("[Pipeline] Final clips generated: %s", len(rendered))
    if len(rendered) == 0:
        logger.warning("[Pipeline] No clips were generated — check logs above.")

    report = {
        "input_video": str(input_video),
        "duration_seconds": round(duration, 2),
        "frames_analyzed": len(frame_samples),
        "clips_created": len(rendered),
        "clips": rendered,
        "log_file": str(log_path),
    }
    _write_json(report_dir / f"{video_stem}_run_report.json", report)
    return report


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load config.json and apply environment overrides."""
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
    """Create required project folders if missing."""
    paths = {
        "raw": PROJECT_ROOT / "raw_clips",
        "processed": PROJECT_ROOT / "processed_clips",
        "final": PROJECT_ROOT / "final_clips",
        "models": PROJECT_ROOT / "models",
        "logs": PROJECT_ROOT / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def resolve_video_path(video_path: str | Path) -> Path:
    """Resolve an input video from absolute, relative, or raw_clips paths."""
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="AI-powered gameplay clip generator")
    parser.add_argument("video", help="Path to a raw gameplay video, e.g. raw_clips/myvideo.mp4")
    parser.add_argument("--config", help="Optional path to config.json", default=None)
    args = parser.parse_args()

    report = run_pipeline(args.video, args.config)
    print("\nDone. Final clips:")
    for clip in report["clips"]:
        print(f"- {clip['final_clip']} (score {clip['score']})")
    print(f"\nLog file: {report['log_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
