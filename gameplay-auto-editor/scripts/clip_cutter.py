"""Cut highlight ranges and render vertical short-form clips with FFmpeg."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List

from scripts.render_settings import merge_render_config, resolve_font_path
from scripts.text_utils import sanitize_overlay_text, wrap_overlay_text

logger = logging.getLogger(__name__)


def process_highlights(
    video_path: str | Path,
    highlights: Iterable[dict],
    processed_dir: str | Path,
    final_dir: str | Path,
    render_config: dict,
) -> List[dict]:
    """Cut raw segments and render one vertical clip per highlight."""
    _ensure_ffmpeg()

    video_path = Path(video_path)
    processed_dir = Path(processed_dir)
    final_dir = Path(final_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    settings = merge_render_config(render_config)
    video_id = _safe_video_id(video_path.stem)
    rendered: list[dict] = []

    for highlight in highlights:
        clip_index = _clip_index(highlight)
        output_names = build_output_names(video_id, clip_index)

        processed_path = processed_dir / output_names["raw"]
        final_path = final_dir / output_names["vertical"]
        metadata_path = final_dir / output_names["metadata"]

        logger.info("Cutting raw segment for %s", output_names["vertical"])
        cut_clip(video_path, processed_path, highlight["start"], highlight["duration"], settings)

        logger.info("Rendering vertical clip %s", final_path.name)
        render_vertical_clip(processed_path, final_path, highlight, settings)

        metadata_path.write_text(json.dumps(highlight, indent=2), encoding="utf-8")
        rendered.append(
            {
                **highlight,
                "video_id": video_id,
                "clip_index": clip_index,
                "processed_clip": str(processed_path),
                "final_clip": str(final_path),
                "metadata": str(metadata_path),
            }
        )

    logger.info("Rendered %s vertical clip(s) to %s", len(rendered), final_dir)
    return rendered


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
    """Extract a highlight segment while preserving audio."""
    settings = merge_render_config(render_config)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(float(start), 0):.2f}",
        "-i",
        str(video_path),
        "-t",
        f"{max(float(duration), 1):.2f}",
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
    _run_ffmpeg(command, stage="cut_clip")


def render_vertical_clip(
    input_path: str | Path,
    output_path: str | Path,
    highlight: dict,
    render_config: dict,
) -> None:
    """Scale, crop, and overlay hook/caption text for 1080x1920 export."""
    settings = merge_render_config(render_config)
    filter_chain = build_vertical_filter_chain(
        hook_text=highlight.get("hook_text", "Wait for it"),
        caption_text=highlight.get("caption_text", highlight.get("summary", "")),
        settings=settings,
    )

    logger.info("FFmpeg filter chain:\n%s", filter_chain)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        filter_chain,
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
    _run_ffmpeg(command, stage="render_vertical_clip", filter_chain=filter_chain)


def get_video_duration(video_path: str | Path) -> float:
    """Return media duration in seconds using ffprobe."""
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
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def build_vertical_filter_chain(
    hook_text: str,
    caption_text: str,
    settings: dict | None = None,
) -> str:
    """Build a Windows-safe FFmpeg filter chain for vertical short-form export."""
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

    filters: list[str] = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "setsar=1",
    ]

    hook_lines = wrap_overlay_text(
        hook_text.upper(),
        max_chars=int(cfg["hook_max_chars"]),
        max_lines=int(cfg["hook_max_lines"]),
    )
    caption_lines = wrap_overlay_text(
        caption_text,
        max_chars=int(cfg["caption_max_chars"]),
        max_lines=int(cfg["caption_max_lines"]),
    )

    hook_y = top_safe
    hook_line_gap = hook_font + 20
    for line in hook_lines:
        filters.append(
            _drawtext_filter(
                text=line,
                font_size=hook_font,
                y=hook_y,
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )
        hook_y += hook_line_gap

    caption_block_height = len(caption_lines) * caption_font + max(0, len(caption_lines) - 1) * 18
    caption_start_y = max(top_safe + hook_font + 40, height - bottom_safe - caption_block_height)

    for offset, line in enumerate(caption_lines):
        filters.append(
            _drawtext_filter(
                text=line,
                font_size=caption_font,
                y=caption_start_y + offset * (caption_font + 18),
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )

    return ",".join(filters)


def _drawtext_filter(
    text: str,
    font_size: int,
    y: int,
    font_path: str,
    box_color: str,
    box_border: int,
) -> str:
    """Create one drawtext filter segment with sanitized text and escaped font path."""
    sanitized = sanitize_overlay_text(text)
    prefix = "drawtext"
    if font_path:
        prefix = f"drawtext=fontfile={escape_font_path(font_path)}"

    return (
        f"{prefix}:"
        f'text="{sanitized}":'
        f"fontsize={font_size}:"
        "fontcolor=white:"
        "box=1:"
        f"boxcolor={box_color}:"
        f"boxborderw={box_border}:"
        "x=(w-text_w)/2:"
        f"y={y}"
    )


def escape_font_path(path: str) -> str:
    """Escape Windows drive-letter colons for FFmpeg filter syntax."""
    normalized = Path(path).as_posix()
    if len(normalized) >= 2 and normalized[1] == ":":
        return f"{normalized[0]}\\:{normalized[2:]}"
    return normalized.replace(":", "\\:")


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
    """Run FFmpeg/ffprobe and include filter chain details when rendering fails."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)
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
