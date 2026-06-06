"""Shared validation helpers for the clip generation pipeline."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from scripts.render_settings import merge_render_config, resolve_font_path
from scripts.text_utils import validate_filter_chain

logger = logging.getLogger(__name__)


def validate_ffmpeg_filter_support() -> tuple[bool, list[str]]:
    """Verify the installed FFmpeg build supports required video filters."""
    import subprocess

    from scripts.subprocess_utils import run_quiet

    missing: list[str] = []
    result = run_quiet(["ffmpeg", "-hide_banner", "-filters"])
    filters_output = (result.stdout or "") + (result.stderr or "")
    for required in ("drawtext", "zoompan", "minterpolate"):
        if required not in filters_output:
            missing.append(required)
    return len(missing) == 0, missing


def preflight_pipeline(
    input_video: str | Path,
    render_config: dict | None = None,
) -> dict:
    """Verify dependencies and inputs before the pipeline runs."""
    settings = merge_render_config(render_config)
    video_path = Path(input_video)
    checks: dict[str, bool] = {}
    errors: list[str] = []

    checks["video_exists"] = video_path.exists()
    if not checks["video_exists"]:
        errors.append(f"Input video not found: {video_path}")

    checks["ffmpeg"] = shutil.which("ffmpeg") is not None
    if not checks["ffmpeg"]:
        errors.append("ffmpeg is not on PATH.")

    checks["ffprobe"] = shutil.which("ffprobe") is not None
    if not checks["ffprobe"]:
        errors.append("ffprobe is not on PATH.")

    try:
        import cv2  # noqa: F401

        checks["opencv"] = True
    except ImportError:
        checks["opencv"] = False
        errors.append("OpenCV (cv2) is not installed.")

    font_path = resolve_font_path(settings.get("font_candidates"))
    checks["font"] = bool(font_path) and Path(font_path).exists()
    if not checks["font"]:
        errors.append(
            "No overlay font found. Install Arial/DejaVu or update font_candidates in config.json."
        )
    else:
        logger.info("[Validation] Preflight font OK: %s", font_path)

    filters_ok, missing_filters = validate_ffmpeg_filter_support()
    checks["ffmpeg_filters"] = filters_ok
    if not filters_ok:
        errors.append(
            "FFmpeg is missing required filters: "
            + ", ".join(missing_filters)
            + ". Text overlays and viral polish require drawtext (and zoompan/minterpolate)."
        )

    ok = all(checks.values())
    logger.info("[Validation] Preflight checks: %s", checks)
    if errors:
        for message in errors:
            logger.error("[Validation] Preflight failed: %s", message)

    return {"ok": ok, "checks": checks, "errors": errors, "font_path": font_path}


def validate_highlight_timestamps(highlight: dict, video_duration: float) -> None:
    """Confirm highlight start/end fall within the source video duration."""
    start = float(highlight.get("start", 0))
    end = float(highlight.get("end", start + float(highlight.get("duration", 1))))
    timestamp = float(highlight.get("timestamp", start))

    if video_duration <= 0:
        logger.warning(
            "[Validation] Video duration unknown for %s — timestamp bounds not enforced.",
            highlight.get("id"),
        )
        return

    if start < 0 or start > video_duration:
        raise ValueError(
            f"Highlight start {start:.2f}s is outside video duration {video_duration:.2f}s."
        )
    if end > video_duration + 0.05:
        logger.warning(
            "[Validation] Highlight end %.2fs exceeds video duration %.2fs — FFmpeg will clamp.",
            end,
            video_duration,
        )
    if timestamp < 0 or timestamp > video_duration:
        raise ValueError(
            f"Highlight timestamp {timestamp:.2f}s is outside video duration {video_duration:.2f}s."
        )

    logger.info(
        "[Validation] Timestamps OK for %s: t=%.2fs range=%.2fs-%.2fs (video %.2fs)",
        highlight.get("id"),
        timestamp,
        start,
        end,
        video_duration,
    )


def validate_font_path(font_path: str) -> None:
    """Confirm an overlay font file exists before rendering."""
    if not font_path:
        raise FileNotFoundError("No font path resolved — check font_candidates in config.json.")

    path = Path(font_path)
    if not path.exists():
        raise FileNotFoundError(f"Font path does not exist: {font_path}")

    logger.info("[Validation] Font path exists: %s", path.as_posix())


def validate_filter_chain_ready(filter_chain: str) -> None:
    """Confirm the FFmpeg filter chain is non-empty and syntactically valid."""
    if not filter_chain or not filter_chain.strip():
        raise ValueError("Filter chain is empty — nothing to render.")

    validate_filter_chain(filter_chain)
    logger.info("[Validation] Filter chain validated (%s characters).", len(filter_chain))


def validate_processed_clip_exists(processed_path: str | Path) -> None:
    """Confirm the raw cut clip was written to processed_clips."""
    path = Path(processed_path)
    if not path.exists():
        raise FileNotFoundError(f"Raw highlight clip missing in processed_clips: {path}")

    if path.stat().st_size <= 0:
        raise RuntimeError(f"Raw highlight clip is empty: {path}")

    logger.info("[Validation] Raw highlight clip confirmed: %s", path)


def validate_output_file_exists(output_path: str | Path) -> None:
    """Confirm FFmpeg wrote the expected output file."""
    path = Path(output_path)
    if not path.exists() or path.stat().st_size <= 0:
        logger.error("[FFmpeg] Output file missing — render failed.")
        raise RuntimeError(f"Output file missing or empty after FFmpeg: {path}")

    logger.info("[Validation] Output file confirmed: %s", path)
