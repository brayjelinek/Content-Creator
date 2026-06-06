"""End-to-end gameplay clip generation pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict

from dotenv import load_dotenv

from scripts.api_usage_guard import get_usage_summary, reset_video_counter
from scripts.chat_signals import apply_chat_spikes_to_analyses, load_chat_spike_times
from scripts.config_rollout import apply_rollout_defaults, build_features_applied
from scripts.detection_profiles import load_profile, merge_profile_weights
from scripts.clip_metadata import build_clip_report_entry, quality_tier
from scripts.clip_timing import compute_clip_range
from scripts.caption_generator import generate_captions
from scripts.clip_cutter import get_video_duration, process_highlights
from scripts.frame_extractor import extract_frames
from scripts.highlight_detector import detect_highlights
from scripts.logging_utils import setup_pipeline_logging
from scripts.microclip_sampler import extract_microclips
from scripts.moment_validator import enrich_highlight_validation
from scripts.ocr_utils import initialize_ocr
from scripts.pipeline_validation import preflight_pipeline
from scripts.transcription import enrich_highlights_with_transcription
from scripts.ui_events import (
    STAGE_DETECTING,
    STAGE_EXTRACTING,
    STAGE_FINALIZING,
    STAGE_LOADING,
    STAGE_MICROCLIPS,
    STAGE_RENDERING,
    emit_clips_ready,
    emit_highlights_detected,
    emit_progress,
    emit_run_summary,
    emit_ui_notice,
    resolve_clip_paths,
)
from scripts.render_settings import merge_render_config
from scripts.viral_clip_enhancer import enhance_rendered_clip
from scripts.vision_analyzer import VisionAnalyzer

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], None]


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
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Run the full clip generation workflow for one input video."""
    config = load_config(config_path)
    if config_override:
        config = _deep_merge(config, config_override)

    reset_video_counter()
    paths = ensure_project_dirs()
    emit_progress(
        progress_callback,
        stage=STAGE_LOADING,
        percent=2,
        message="Preparing workspace and output folders...",
    )

    input_video = resolve_video_path(video_path)
    video_stem = input_video.stem

    log_path = setup_pipeline_logging(paths["logs"], video_stem)
    logger.info("[Pipeline] Writing logs to %s", log_path)

    emit_progress(
        progress_callback,
        stage=STAGE_LOADING,
        percent=5,
        message=f"Loading video: {input_video.name}",
    )

    render_config = merge_render_config(config.get("rendering", {}))
    highlight_config = config.get("highlight_detection", {})
    detection_profile = load_profile(highlight_config.get("game_profile"))
    highlight_config = merge_profile_weights(highlight_config, detection_profile)
    render_config["facecam_corners"] = detection_profile.get("facecam_corners")
    logger.info("[Pipeline] Detection profile: %s", detection_profile.get("label", detection_profile.get("id")))

    preflight = preflight_pipeline(input_video, render_config)
    if not preflight["ok"]:
        message = "; ".join(preflight["errors"])
        logger.error("[Pipeline] Preflight failed: %s", message)
        raise RuntimeError(message)

    ocr_status = initialize_ocr(config.get("ocr", {}))
    if not ocr_status.get("available"):
        emit_ui_notice(progress_callback, "[UI] OCR unavailable — skipping")

    frame_dir = paths["processed"] / "frames" / video_stem
    report_dir = paths["processed"] / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    vision_config = config.get("vision", {})
    microclip_config = vision_config.get("microclip_sampling", {})

    samples = _extract_analysis_samples(
        input_video=input_video,
        frame_dir=frame_dir,
        vision_config=vision_config,
        microclip_config=microclip_config,
        detection_profile=detection_profile,
        progress_callback=progress_callback,
    )
    if not samples:
        logger.error("[Pipeline] No samples extracted — check that the input is a valid video file.")
        raise RuntimeError("No samples were extracted. Check that the input is a valid video file.")

    sample_label = "microclip" if samples[0].get("clip_path") else "frame"
    logger.info("[Pipeline] Extracted %s %s sample(s) from %s", len(samples), sample_label, input_video.name)

    provider = vision_config.get("provider", "heuristic")
    emit_progress(
        progress_callback,
        stage=STAGE_DETECTING,
        percent=35,
        message=f"Analyzing {len(samples)} sample(s) with {provider} vision...",
    )
    if provider == "heuristic":
        logger.info("[Pipeline] Running heuristic analysis...")
    else:
        logger.info("[Pipeline] Running %s analysis on %s %s sample(s)...", provider, len(samples), sample_label)
    analyzer = VisionAnalyzer(vision_config)
    analyses = analyzer.analyze_samples(samples)
    _write_json(report_dir / f"{video_stem}_analysis.json", analyses)

    chat_cfg = config.get("chat_signals", {})
    if chat_cfg.get("enabled"):
        spike_times = load_chat_spike_times(chat_cfg.get("chat_log_path"), chat_cfg)
        apply_chat_spikes_to_analyses(analyses, spike_times, chat_cfg)
        if spike_times:
            emit_ui_notice(progress_callback, f"[UI] Chat spikes detected: {len(spike_times)} window(s)")

    ai_fallbacks = sum(1 for item in analyses if item.get("provider_error"))
    if ai_fallbacks:
        logger.info("[Hybrid] Using fallback heuristic scoring")
        emit_ui_notice(progress_callback, "[UI] AI scoring failed — fallback to heuristic")

    duration = get_video_duration(input_video)
    logger.info("[Pipeline] Video duration: %.2fs", duration)
    emit_progress(
        progress_callback,
        stage=STAGE_DETECTING,
        percent=50,
        message="Scoring highlight moments...",
    )
    highlights = detect_highlights(analyses, duration, highlight_config)
    highlights = _ensure_minimum_highlights(highlights, analyses, samples, duration, highlight_config)
    logger.info("[Pipeline] Highlights detected: %s", len(highlights))
    emit_highlights_detected(progress_callback, count=len(highlights), percent=55)

    for highlight in highlights:
        highlight["quality_tier"] = quality_tier(highlight)
        logger.info(
            "[Pipeline] Highlight %s at %.2fs (score %.2f, %.2fs-%.2fs)",
            highlight.get("id"),
            float(highlight.get("timestamp", 0)),
            float(highlight.get("score", 0)),
            float(highlight.get("start", 0)),
            float(highlight.get("end", 0)),
        )

    emit_progress(
        progress_callback,
        stage=STAGE_RENDERING,
        percent=60,
        message="Generating hooks and captions...",
    )
    transcription_cfg = config.get("transcription", {})
    if transcription_cfg.get("enabled"):
        enrich_highlights_with_transcription(
            highlights,
            input_video,
            transcription_cfg,
            vision_config,
        )

    logger.info("[Pipeline] Generating hooks and captions")
    captioned_highlights = generate_captions(
        highlights,
        video_name=video_stem,
        add_hashtags=bool(render_config.get("add_hashtags", True)),
        render_config=render_config,
    )
    viral_cfg = render_config.get("viral_enhancements", {})
    captioned_highlights = [
        enrich_highlight_validation(highlight, viral_cfg) for highlight in captioned_highlights
    ]
    _write_json(report_dir / f"{video_stem}_highlights.json", captioned_highlights)

    paths["final"].mkdir(parents=True, exist_ok=True)
    emit_progress(
        progress_callback,
        stage=STAGE_RENDERING,
        percent=65,
        message=f"Rendering {len(captioned_highlights)} clip(s) with FFmpeg...",
    )
    logger.info("[Pipeline] Starting clip rendering...")
    rendered = process_highlights(
        video_path=input_video,
        highlights=captioned_highlights,
        processed_dir=paths["processed"],
        final_dir=paths["final"],
        render_config=render_config,
        video_duration=duration,
    )

    used_fallback_render = False
    if len(rendered) == 0:
        logger.warning("[Pipeline] Render produced zero clips — attempting fallback clip.")
        fallback_highlight = _build_fallback_highlight(analyses, samples, duration, highlight_config)
        fallback_captioned = generate_captions(
            [fallback_highlight],
            video_name=video_stem,
            add_hashtags=bool(render_config.get("add_hashtags", True)),
            render_config=render_config,
        )
        rendered = process_highlights(
            video_path=input_video,
            highlights=fallback_captioned,
            processed_dir=paths["processed"],
            final_dir=paths["final"],
            render_config=render_config,
            video_duration=duration,
        )
        used_fallback_render = bool(rendered)
        if used_fallback_render:
            logger.info("[Pipeline] Fallback clip generated")
            highlights = [fallback_highlight]

    for clip in rendered:
        logger.info(
            "[Pipeline] Final clip ready: %s (score %s)",
            clip["final_clip"],
            clip.get("score"),
        )
        try:
            enhanced = enhance_rendered_clip(clip["final_clip"], clip, render_config)
            if enhanced:
                clip["viral_enhanced"] = True
                clip["quality_tier"] = quality_tier(clip)
                emit_ui_notice(
                    progress_callback,
                    f"[UI] Clip polished: {Path(clip['final_clip']).name}",
                )
            elif not clip.get("overlay_applied", True):
                emit_ui_notice(
                    progress_callback,
                    "[UI] Overlay render used fallback — check log for [Enhancer] polish status",
                )
        except Exception as exc:  # noqa: BLE001 - enhancement must never break pipeline
            logger.warning("[Enhancer] Skipped enhancement for %s: %s", clip.get("id"), exc)

    emit_progress(
        progress_callback,
        stage=STAGE_FINALIZING,
        percent=95,
        message="Finalizing output files...",
    )
    logger.info("[Pipeline] Final clips generated: %s", len(rendered))
    failure_reason = None
    if len(rendered) == 0:
        failure_reason = "render_failed"
        logger.warning("[Pipeline] No clips were generated — check logs above.")
        logger.warning("[Pipeline] Stage that failed: FFmpeg vertical render")
        logger.warning("[Pipeline] Log file: %s", log_path)
        if highlights:
            logger.warning(
                "[Pipeline] %s highlight(s) were detected but rendering produced zero clips. "
                "Search the log for '[FFmpeg] stderr' or 'No option name near'.",
                len(highlights),
            )

    output_dir = str(paths["final"].resolve())
    clips_ready = resolve_clip_paths(rendered, paths["final"])
    emit_clips_ready(
        progress_callback,
        clip_paths=clips_ready,
        clips=rendered,
        output_dir=output_dir,
        percent=100,
    )

    detection_mode = provider
    if ai_fallbacks:
        detection_mode = f"{provider}_heuristic_fallback"

    quality_tier_counts = _count_quality_tiers(rendered)
    features_applied = build_features_applied(config, {"enhancements_summary": _summarize_run_enhancements(rendered)})

    report = {
        "input_video": str(input_video),
        "duration_seconds": round(duration, 2),
        "frames_analyzed": len(samples),
        "samples_analyzed": len(samples),
        "highlights_detected": len(highlights),
        "clips_created": len(rendered),
        "clips": rendered,
        "clip_summaries": [build_clip_report_entry(clip) for clip in rendered],
        "clips_ready": clips_ready,
        "output_dir": output_dir,
        "log_file": str(log_path),
        "failure_reason": failure_reason,
        "used_fallback": used_fallback_render or any(
            highlight.get("selection_mode", "").startswith("fallback") for highlight in highlights
        ),
        "detection_mode": detection_mode,
        "platform_preset": render_config.get("platform_preset", "generic"),
        "theme": render_config.get("theme", "default"),
        "game_profile": detection_profile.get("id", "generic"),
        "api_usage": get_usage_summary(vision_config),
        "enhancements_summary": _summarize_run_enhancements(rendered),
        "quality_tier_counts": quality_tier_counts,
        "features_applied": features_applied,
    }
    _write_json(report_dir / f"{video_stem}_run_report.json", report)
    emit_run_summary(progress_callback, report=report)
    return report


def _extract_analysis_samples(
    *,
    input_video: Path,
    frame_dir: Path,
    vision_config: dict,
    microclip_config: dict,
    detection_profile: dict | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """Extract microclips by default, with safe fallback to legacy frame sampling."""
    use_microclips = bool(microclip_config.get("enabled", True))
    jpeg_quality = int(vision_config.get("jpeg_quality", 85))

    if use_microclips:
        try:
            emit_progress(
                progress_callback,
                stage=STAGE_MICROCLIPS,
                percent=12,
                message="Sampling short gameplay microclips...",
            )
            logger.info("[Pipeline] Extracting microclips...")
            microclip_dir = frame_dir.parent / "microclips" / frame_dir.name
            samples = extract_microclips(
                input_video,
                microclip_dir,
                interval_seconds=float(microclip_config.get("interval_seconds", 1.0)),
                clip_duration=float(microclip_config.get("duration_seconds", 1.5)),
                max_samples=int(microclip_config.get("max_samples", vision_config.get("max_frames_to_analyze", 60))),
                jpeg_quality=jpeg_quality,
                detection_profile=detection_profile,
            )
            if samples:
                emit_progress(
                    progress_callback,
                    stage=STAGE_MICROCLIPS,
                    percent=28,
                    message=f"Sampled {len(samples)} microclip(s) for analysis.",
                )
                return samples
            logger.warning("[Pipeline] Microclip sampling returned zero samples — falling back to frames.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Pipeline] Microclip sampling failed — falling back to frames: %s", exc)

    emit_progress(
        progress_callback,
        stage=STAGE_EXTRACTING,
        percent=15,
        message="Extracting frames from gameplay video...",
    )
    logger.info("[Pipeline] Extracting frames...")
    frames = extract_frames(
        input_video,
        frame_dir,
        interval_seconds=float(vision_config.get("analysis_interval_seconds", 3)),
        max_frames=int(vision_config.get("max_frames_to_analyze", 24)),
        jpeg_quality=jpeg_quality,
    )
    emit_progress(
        progress_callback,
        stage=STAGE_EXTRACTING,
        percent=28,
        message=f"Extracted {len(frames)} frame(s) for analysis.",
    )
    return frames


def _ensure_minimum_highlights(
    highlights: list[dict],
    analyses: list[dict],
    samples: list[dict],
    duration: float,
    highlight_config: dict,
) -> list[dict]:
    """Guarantee at least one highlight candidate before rendering."""
    if highlights:
        return highlights

    logger.warning("[Pipeline] No highlights detected — using fallback clip.")
    fallback = _build_fallback_highlight(analyses, samples, duration, highlight_config)
    logger.info("[Pipeline] Fallback clip generated at %.2fs-%.2fs", fallback["start"], fallback["end"])
    return [fallback]


def _build_fallback_highlight(
    analyses: list[dict],
    samples: list[dict],
    duration: float,
    highlight_config: dict,
) -> dict:
    """Build a guaranteed fallback highlight from the best sample or a default segment."""
    selection_mode = "fallback_default_segment"
    timestamp = duration * 0.15 if duration > 0 else 0.0
    source_frame = None
    source_clip = None
    score = 1.0
    summary = "Fallback gameplay segment."

    if analyses:
        best = max(
            analyses,
            key=lambda item: float(item.get("final_score", item.get("viral_score", item.get("score", 0)))),
        )
        timestamp = float(best.get("timestamp", timestamp))
        source_frame = best.get("poster_frame_path") or best.get("frame_path")
        source_clip = best.get("clip_path")
        score = float(best.get("final_score", best.get("viral_score", 1)))
        summary = best.get("summary", summary)
        selection_mode = "fallback_best_microclip"
    elif samples:
        best = max(samples, key=lambda item: float(item.get("motion_score", 0)))
        timestamp = float(best.get("timestamp", timestamp))
        source_frame = best.get("poster_frame_path") or best.get("frame_path")
        source_clip = best.get("clip_path")
        score = float(best.get("motion_score", 1))
        selection_mode = "fallback_best_sample"

    if selection_mode == "fallback_default_segment" and duration > 0:
        start = duration * 0.10
        end = duration * 0.20
        start, end = compute_clip_range((start + end) / 2, duration, highlight_config)
    else:
        start, end = compute_clip_range(timestamp, duration, highlight_config)

    return {
        "id": "highlight_fallback",
        "timestamp": round(timestamp, 2),
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(end - start, 2),
        "score": round(score, 2),
        "categories": ["fallback"],
        "summary": summary,
        "reason": "Automatic fallback clip when no highlights were detected.",
        "scores": {},
        "score_breakdown": {},
        "source_frame": source_frame,
        "source_clip": source_clip,
        "selection_mode": selection_mode,
        "quality_tier": "fallback",
    }


def _summarize_run_enhancements(clips: list[dict]) -> dict[str, int]:
    summary = {
        "overlay_applied": 0,
        "viral_enhanced": 0,
        "viral_slowmo_applied": 0,
        "viral_captions_burned": 0,
        "viral_sound_effect_applied": 0,
        "smart_reframe_applied": 0,
        "viral_ass_captions_applied": 0,
    }
    for clip in clips:
        for key in summary:
            if clip.get(key):
                summary[key] += 1
    return summary


def _count_quality_tiers(clips: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for clip in clips:
        tier = str(clip.get("quality_tier") or quality_tier(clip))
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load config.json and apply environment overrides."""
    load_dotenv(PROJECT_ROOT / ".env")
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.json"
    bundled_config = _load_bundled_config()
    if not path.exists() and not config_path and bundled_config:
        config = bundled_config
    elif path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
        if bundled_config and not config_path:
            config = _deep_merge(bundled_config, config)
    elif bundled_config:
        config = bundled_config
    else:
        raise FileNotFoundError(f"Config file not found: {path}")
    return apply_rollout_defaults(_apply_env_overrides(config))


def _load_bundled_config() -> Dict[str, Any] | None:
    bundled_path = BUNDLED_ROOT / "config.json"
    if bundled_path.exists():
        return json.loads(bundled_path.read_text(encoding="utf-8"))
    return None


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
