"""Safe progress and completion events for desktop UI updates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], None]

STAGE_LOADING = "loading_video"
STAGE_EXTRACTING = "extracting_frames"
STAGE_MICROCLIPS = "processing_microclips"
STAGE_DETECTING = "detecting_highlights"
STAGE_RENDERING = "rendering_clips"
STAGE_FINALIZING = "finalizing"


def emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: str,
    percent: int,
    message: str,
) -> None:
    """Emit a non-blocking progress update for the UI."""
    percent = max(0, min(100, int(percent)))
    event = {
        "type": "progress",
        "stage": stage,
        "percent": percent,
        "message": message,
    }
    try:
        if callback:
            callback(event)
        logger.info("[UI] Progress event emitted: %s%% - %s", percent, message)
    except Exception as exc:  # noqa: BLE001 - UI must never break pipeline
        logger.debug("[UI] Progress callback failed: %s", exc)


def emit_highlights_detected(
    callback: ProgressCallback | None,
    *,
    count: int,
    percent: int = 55,
) -> None:
    """Notify UI that highlight detection finished."""
    message = f"Detected {count} highlight moment(s)."
    event = {
        "type": "highlights_detected",
        "stage": STAGE_DETECTING,
        "percent": percent,
        "count": count,
        "message": message,
    }
    try:
        if callback:
            callback(event)
        logger.info("[UI] Progress event emitted: %s%% - %s", percent, message)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[UI] Highlights callback failed: %s", exc)


def emit_clips_ready(
    callback: ProgressCallback | None,
    *,
    clip_paths: list[str],
    clips: list[dict] | None = None,
    output_dir: str | None = None,
    percent: int = 100,
) -> None:
    """Notify UI that final clips are ready to display."""
    resolved = [str(Path(path).resolve()) for path in clip_paths if path]
    event = {
        "type": "clips_ready",
        "stage": STAGE_FINALIZING,
        "percent": percent,
        "clips_ready": resolved,
        "clips": clips or [],
        "count": len(resolved),
        "output_dir": output_dir,
        "message": f"{len(resolved)} clip(s) ready to review.",
    }
    try:
        if callback:
            callback(event)
        logger.info("[UI] Clips ready: %s clips", len(resolved))
        emit_refresh_clips_ui(
            callback,
            clip_paths=resolved,
            clips=clips or [],
            output_dir=output_dir,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[UI] Clips ready callback failed: %s", exc)


def emit_refresh_clips_ui(
    callback: ProgressCallback | None,
    *,
    clip_paths: list[str],
    clips: list[dict] | None = None,
    output_dir: str | None = None,
) -> None:
    """Force the desktop UI to refresh the clip review panel."""
    event = {
        "type": "refresh_clips_ui",
        "clips_ready": clip_paths,
        "clips": clips or [],
        "count": len(clip_paths),
        "output_dir": output_dir,
        "message": f"{len(clip_paths)} clip(s) ready to review.",
    }
    try:
        if callback:
            callback(event)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[UI] Refresh clips callback failed: %s", exc)


def emit_ui_notice(callback: ProgressCallback | None, message: str) -> None:
    """Emit a human-readable UI notice without changing stage percent."""
    event = {"type": "notice", "message": message}
    try:
        if callback:
            callback(event)
        logger.info("[UI] %s", message)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[UI] Notice callback failed: %s", exc)


def resolve_clip_paths(clips: list[dict], final_dir: Path | None = None) -> list[str]:
    """Resolve absolute clip paths from rendered clip metadata."""
    resolved: list[str] = []
    for clip in clips:
        raw_path = clip.get("final_clip")
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute() and final_dir:
            path = final_dir / path.name
        if path.exists():
            resolved.append(str(path.resolve()))
        elif Path(raw_path).exists():
            resolved.append(str(Path(raw_path).resolve()))
    return resolved
