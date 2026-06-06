"""Cut highlight ranges and render vertical short-form clips with FFmpeg."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List

from scripts.pipeline_validation import (
    validate_filter_chain_ready,
    validate_font_path,
    validate_highlight_timestamps,
    validate_output_file_exists,
    validate_processed_clip_exists,
)
from scripts.render_settings import OUTPUT_WIDTH, merge_render_config, resolve_font_path
from scripts.smart_reframe import apply_smart_reframe, merge_reframe_settings
from scripts.subprocess_utils import run_quiet
from scripts.text_utils import sanitize_overlay_text, wrap_overlay_text

logger = logging.getLogger(__name__)

# Root cause (log 232410 / Windows AppData logs):
# FFmpeg drawtext x-expressions with unescaped commas, e.g.
#   x=max(120,min(w-text_w-120,(w-text_w)/2))
# are parsed as filter separators. FFmpeg then throws:
#   [AVFilterGraph] No option name near '250'
# Fix: never use commas inside drawtext options; center with (w-text_w)/2
# and pass the filter chain via -filter_script:v on Windows for reliability.


def process_highlights(
    video_path: str | Path,
    highlights: Iterable[dict],
    processed_dir: str | Path,
    final_dir: str | Path,
    render_config: dict,
    video_duration: float | None = None,
) -> List[dict]:
    """Render one vertical clip per highlight, continuing when one render fails."""
    settings = merge_render_config(render_config)
    video_id = _safe_video_id(Path(video_path).stem)
    rendered: list[dict] = []

    for highlight in highlights:
        try:
            clip = process_single_highlight(
                video_path=video_path,
                highlight=highlight,
                processed_dir=processed_dir,
                final_dir=final_dir,
                render_config=settings,
                video_id=video_id,
                video_duration=video_duration,
            )
            if clip:
                rendered.append(clip)
        except Exception as exc:  # noqa: BLE001 - continue remaining highlights
            logger.error("[FFmpeg] Highlight %s failed: %s", highlight.get("id"), exc)
            if isinstance(exc, RuntimeError) and "STDERR:" in str(exc):
                stderr = str(exc).split("STDERR:", 1)[-1].strip()
                logger.error("[FFmpeg] stderr: %s", stderr)

    logger.info("[FFmpeg] Rendered %s vertical clip(s) to %s", len(rendered), final_dir)
    return rendered


def process_single_highlight(
    video_path: str | Path,
    highlight: dict,
    processed_dir: str | Path,
    final_dir: str | Path,
    render_config: dict,
    video_id: str | None = None,
    video_duration: float | None = None,
) -> dict | None:
    """Cut and render exactly one highlight into final_clips."""
    _ensure_ffmpeg()

    video_path = Path(video_path)
    processed_dir = Path(processed_dir)
    final_dir = Path(final_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    settings = merge_render_config(render_config)
    video_id = video_id or _safe_video_id(video_path.stem)
    clip_index = _clip_index(highlight)
    output_names = build_output_names(video_id, clip_index)

    processed_path = processed_dir / output_names["raw"]
    final_path = final_dir / output_names["vertical"]
    metadata_path = final_dir / output_names["metadata"]

    if video_duration is None:
        video_duration = get_video_duration(video_path)

    validate_highlight_timestamps(highlight, video_duration)

    logger.info("[FFmpeg] Cutting raw segment for %s", output_names["vertical"])
    cut_clip(video_path, processed_path, highlight["start"], highlight["duration"], settings)
    validate_processed_clip_exists(processed_path)

    render_source = processed_path
    render_settings = merge_reframe_settings(settings, processed_path)
    if render_settings.get("reframe_analysis"):
        reframed_path = processed_path.with_name(f"{processed_path.stem}_reframed.mp4")
        if apply_smart_reframe(processed_path, reframed_path, render_settings):
            render_source = reframed_path
            highlight = dict(highlight)
            highlight["smart_reframe_applied"] = True
            highlight["reframe_layout"] = render_settings["reframe_analysis"].get("layout")
            highlight["reframe_corner"] = render_settings["reframe_analysis"].get("corner")

    logger.info("[FFmpeg] Rendering vertical clip %s", final_path.name)
    overlay_applied = False
    try:
        render_vertical_clip(
            render_source,
            final_path,
            highlight,
            render_settings,
            video_duration=video_duration,
        )
        overlay_applied = True
    except Exception as exc:
        logger.error("[FFmpeg] Overlay render failed for %s: %s", highlight.get("id"), exc)
        logger.warning("[FFmpeg] Retrying %s without text overlays (vertical-only fallback).", final_path.name)
        render_vertical_clip_base(render_source, final_path, render_settings)

    validate_vertical_output(
        final_path,
        expected_width=int(settings["width"]),
        expected_height=int(settings["height"]),
    )
    has_audio = probe_has_audio(final_path)
    if not has_audio:
        logger.info("[FFmpeg] No audio stream detected in %s (video-only clip)", final_path.name)

    metadata = dict(highlight)
    metadata["overlay_applied"] = overlay_applied
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        **highlight,
        "video_id": video_id,
        "clip_index": clip_index,
        "processed_clip": str(processed_path),
        "final_clip": str(final_path),
        "metadata": str(metadata_path),
        "has_audio": has_audio,
        "overlay_applied": overlay_applied,
    }


def build_output_names(video_id: str, clip_index: str) -> dict[str, str]:
    """Standardize output filenames for raw, vertical, and metadata files."""
    stem = f"{video_id}_highlight_{clip_index}"
    return {
        "raw": f"{stem}_raw.mp4",
        "vertical": f"{stem}_vertical.mp4",
        "metadata": f"{stem}.json",
    }


def cut_clip(
    video_path: str | Path,
    output_path: str | Path,
    start: float,
    duration: float,
    render_config: dict | None = None,
) -> None:
    """Extract a highlight segment while preserving audio when available."""
    settings = merge_render_config(render_config)
    safe_start = max(float(start), 0)
    safe_duration = max(float(duration), 1)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-ss",
        f"{safe_start:.2f}",
        "-t",
        f"{safe_duration:.2f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        str(settings["preset"]),
        "-crf",
        str(settings["video_crf"]),
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    logger.info("[FFmpeg] Running command: %s", " ".join(command))
    _run_ffmpeg(command, stage="cut_clip")
    validate_output_file_exists(output_path)


def render_vertical_clip(
    input_path: str | Path,
    output_path: str | Path,
    highlight: dict,
    render_config: dict,
    video_duration: float | None = None,
) -> None:
    """Scale, crop, and overlay hook/caption text for 1080x1920 export."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    settings = merge_render_config(render_config)
    font_path = resolve_font_path(settings.get("font_candidates"))

    filter_chain = build_vertical_filter_chain(
        hook_text=highlight.get("hook_text", "Wait for it"),
        caption_text=highlight.get("caption_text", highlight.get("summary", "")),
        caption_lines=highlight.get("caption_lines"),
        settings=settings,
    )

    if not input_path.exists():
        logger.error("[FFmpeg] Input file missing: %s", input_path)
        raise FileNotFoundError(f"Input file missing: {input_path}")

    logger.info("[FFmpeg] Input file exists: %s", input_path)
    logger.info("[FFmpeg] Output path: %s", output_path)
    logger.info("[FFmpeg] Filter chain: %s", filter_chain)

    validate_font_path(font_path)
    validate_filter_chain_ready(filter_chain)
    if video_duration is not None:
        validate_highlight_timestamps(highlight, video_duration)

    _execute_vertical_render(
        input_path=input_path,
        output_path=output_path,
        filter_chain=filter_chain,
        settings=settings,
        stage="render_vertical_clip",
    )


def render_vertical_clip_base(
    input_path: str | Path,
    output_path: str | Path,
    render_config: dict,
) -> None:
    """Render a vertical clip without drawtext overlays (fail-safe fallback)."""
    settings = merge_render_config(render_config)
    filter_chain = build_base_vertical_filter_chain(settings)
    logger.info("[FFmpeg] Fallback vertical filter chain: %s", filter_chain)
    _execute_vertical_render(
        input_path=input_path,
        output_path=output_path,
        filter_chain=filter_chain,
        settings=settings,
        stage="render_vertical_clip_base",
    )


def build_base_vertical_filter_chain(settings: dict | None = None) -> str:
    """Build scale/crop chain only — no drawtext, no commas in expressions."""
    return ",".join(_base_vertical_filters(settings))


def _base_vertical_filters(settings: dict | None = None) -> list[str]:
    cfg = merge_render_config(settings)
    width = int(cfg["width"])
    height = int(cfg["height"])
    return [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "setsar=1",
    ]


def build_vertical_filter_chain(
    hook_text: str,
    caption_text: str,
    settings: dict | None = None,
    caption_lines: list[str] | None = None,
) -> str:
    """Build a validated FFmpeg filter chain using list-based construction only."""
    cfg = merge_render_config(settings)
    width = int(cfg["width"])
    height = int(cfg["height"])
    top_safe = int(cfg["top_safe_zone"])
    bottom_safe = int(cfg["bottom_safe_zone"])
    hook_font = int(cfg["top_hook_font_size"])
    caption_font = int(cfg["caption_font_size"])
    box_color = str(cfg["text_box_color"])
    box_border = int(cfg["text_box_border"])
    font_path = resolve_font_path(cfg.get("font_candidates"))
    side_safe = int(cfg["side_safe_zone"])

    filters: list[str] = []
    filters.extend(_base_vertical_filters(cfg))

    hook_max_chars = _max_chars_for_safe_width(side_safe, hook_font, int(cfg["hook_max_chars"]))
    caption_max_chars = _max_chars_for_safe_width(side_safe, caption_font, int(cfg["caption_max_chars"]))

    hook_lines = wrap_overlay_text(
        hook_text.upper(),
        max_chars=hook_max_chars,
        max_lines=int(cfg["hook_max_lines"]),
    )
    if caption_lines:
        wrapped_caption_lines = [sanitize_overlay_text(line) for line in caption_lines]
    else:
        wrapped_caption_lines = wrap_overlay_text(
            caption_text,
            max_chars=caption_max_chars,
            max_lines=int(cfg["caption_max_lines"]),
        )

    centered_x = _centered_x_expression()

    hook_y = top_safe
    hook_line_gap = hook_font + 20
    max_hook_y = top_safe + (int(cfg["hook_max_lines"]) * hook_line_gap)
    for line in hook_lines:
        if hook_y + hook_font > max_hook_y:
            break
        filters.append(
            _build_drawtext_filter(
                text=line,
                font_size=hook_font,
                y=hook_y,
                x=centered_x,
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )
        hook_y += hook_line_gap

    caption_line_gap = caption_font + 18
    caption_y_anchor = height - bottom_safe
    wrapped_lines = wrapped_caption_lines[: int(cfg["caption_max_lines"])]
    caption_positions = _caption_line_positions(
        line_count=len(wrapped_lines),
        caption_font=caption_font,
        line_gap=caption_line_gap,
        anchor_y=caption_y_anchor,
    )

    for line, line_y in zip(wrapped_lines, caption_positions):
        if line_y < top_safe + hook_font + 20:
            break
        filters.append(
            _build_drawtext_filter(
                text=line,
                font_size=caption_font,
                y=line_y,
                x=centered_x,
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )

    return ",".join(filters)


def _centered_x_expression() -> str:
    """Center text horizontally without commas (commas break FFmpeg filter parsing)."""
    return "(w-text_w)/2"


def _max_chars_for_safe_width(side_safe: int, font_size: int, configured_max: int) -> int:
    """Estimate readable character count inside horizontal safe margins."""
    usable = max(OUTPUT_WIDTH - (2 * side_safe), 400)
    estimated = max(12, int(usable / max(font_size * 0.55, 1)))
    return min(configured_max, estimated)


def _caption_line_positions(
    line_count: int,
    caption_font: int,
    line_gap: int,
    anchor_y: int,
) -> list[int]:
    """Place caption lines upward from the bottom safe-zone boundary."""
    if line_count <= 0:
        return []

    positions: list[int] = []
    current_y = anchor_y - caption_font
    for _ in range(line_count):
        positions.insert(0, current_y)
        current_y -= line_gap
    return positions


def _build_drawtext_filter(
    text: str,
    font_size: int,
    y: int,
    font_path: str,
    box_color: str,
    box_border: int,
    x: str = "(w-text_w)/2",
) -> str:
    """Build one drawtext filter segment from a list of options."""
    sanitized = sanitize_overlay_text(text)
    options: list[str] = []

    if font_path:
        options.append(f"fontfile={format_font_path(font_path)}")

    options.extend(
        [
            f'text="{sanitized}"',
            f"fontsize={font_size}",
            "fontcolor=white",
            "box=1",
            f"boxcolor={box_color}",
            f"boxborderw={box_border}",
            f"x={x}",
            f"y={y}",
        ]
    )

    return "drawtext=" + ":".join(options)


def format_font_path(path: str) -> str:
    """Format font paths with forward slashes and escaped drive-letter colons."""
    normalized = Path(path).as_posix()
    if len(normalized) >= 2 and normalized[1] == ":":
        return f"{normalized[0]}\\:{normalized[2:]}"
    return normalized


def _execute_vertical_render(
    *,
    input_path: Path,
    output_path: Path,
    filter_chain: str,
    settings: dict,
    stage: str,
) -> None:
    """Run FFmpeg vertical render using a filter script file for Windows reliability."""
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        str(settings["preset"]),
        "-crf",
        str(settings["video_crf"]),
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    filter_script = _write_filter_script(filter_chain)
    insert_at = command.index("-map")
    command[insert_at:insert_at] = ["-filter_script:v", str(filter_script)]

    try:
        logger.info("[FFmpeg] Running command: %s", " ".join(command))
        logger.info("[FFmpeg] Filter script file: %s", filter_script)
        _run_ffmpeg(command, stage=stage, filter_chain=filter_chain)
        validate_output_file_exists(output_path)
    except Exception as exc:
        logger.error("[FFmpeg] Render failed during %s: %s", stage, exc)
        logger.error("[FFmpeg] Command: %s", " ".join(command))
        logger.error("[FFmpeg] Filter chain: %s", filter_chain)
        if isinstance(exc, RuntimeError) and "STDERR:" in str(exc):
            stderr = str(exc).split("STDERR:", 1)[-1].strip()
            logger.error("[FFmpeg] stderr: %s", stderr)
        raise
    finally:
        filter_script.unlink(missing_ok=True)


def _write_filter_script(filter_chain: str) -> Path:
    """Write the filter chain to a temp file for -filter_script:v."""
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="gae_filter_",
        delete=False,
        encoding="utf-8",
    )
    handle.write(filter_chain)
    handle.flush()
    handle.close()
    return Path(handle.name)


def get_video_duration(video_path: str | Path) -> float:
    """Return media duration in seconds using ffprobe with OpenCV fallback."""
    _ensure_ffprobe()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = _run_ffmpeg(command, stage="get_video_duration")
    raw = result.stdout.strip()
    if not raw:
        logger.warning("[FFmpeg] ffprobe returned empty duration for %s", video_path)
        return _opencv_duration_fallback(video_path)

    try:
        duration = float(raw)
    except ValueError:
        logger.warning("[FFmpeg] Could not parse duration %r for %s", raw, video_path)
        return _opencv_duration_fallback(video_path)

    if duration <= 0:
        logger.warning("[FFmpeg] Non-positive duration %.2fs for %s", duration, video_path)
        return _opencv_duration_fallback(video_path)

    return duration


def _opencv_duration_fallback(video_path: str | Path) -> float:
    """Fallback duration probe when ffprobe fails."""
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error("[FFmpeg] OpenCV could not open video for duration fallback: %s", video_path)
            return 0.0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        duration = frame_count / fps if frame_count else 0.0
        logger.info("[FFmpeg] OpenCV duration fallback for %s: %.2fs", video_path, duration)
        return duration
    except Exception as exc:  # noqa: BLE001
        logger.error("[FFmpeg] Duration fallback failed for %s: %s", video_path, exc)
        return 0.0


def validate_vertical_output(path: str | Path, expected_width: int, expected_height: int) -> None:
    """Confirm rendered clip matches the target vertical resolution."""
    _ensure_ffprobe()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    result = _run_ffmpeg(command, stage="validate_vertical_output")
    parts = result.stdout.strip().split("x")
    if len(parts) != 2:
        raise RuntimeError(f"Could not validate output resolution for {path}")

    width, height = int(parts[0]), int(parts[1])
    if width != expected_width or height != expected_height:
        raise RuntimeError(
            f"Output resolution mismatch for {path}: got {width}x{height}, "
            f"expected {expected_width}x{expected_height}"
        )


def probe_has_audio(path: str | Path) -> bool:
    """Return True when the clip contains an audio stream."""
    _ensure_ffprobe()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    result = _run_ffmpeg(command, stage="probe_has_audio")
    return bool(result.stdout.strip())


def _clip_index(highlight: dict) -> str:
    clip_id = str(highlight.get("id", "highlight_01"))
    if clip_id.startswith("highlight_"):
        return clip_id.split("_", 1)[1]
    return clip_id


def _safe_video_id(name: str) -> str:
    allowed = []
    for char in str(name).lower():
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        elif char in {" ", "."}:
            allowed.append("_")
    return "".join(allowed).strip("_") or "video"


def _ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required but was not found on PATH.")


def _ensure_ffprobe() -> None:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required but was not found on PATH.")


def _run_ffmpeg(
    command: list[str],
    *,
    stage: str,
    filter_chain: str | None = None,
) -> subprocess.CompletedProcess:
    """Run FFmpeg/ffprobe and include command and filter details on failure."""
    result = run_quiet(command, stage=stage, filter_chain=filter_chain)
    if result.returncode != 0:
        details = [
            f"FFmpeg stage failed: {stage}",
            "Command:",
            " ".join(command),
        ]
        if filter_chain:
            details.extend(["Filter chain:", filter_chain])
        details.extend(["STDOUT:", result.stdout, "STDERR:", result.stderr])
        raise RuntimeError("\n".join(details))
    return result
