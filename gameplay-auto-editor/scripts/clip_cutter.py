"""Cut highlight ranges and render vertical clips with FFmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List


def process_highlights(
    video_path: str | Path,
    highlights: Iterable[dict],
    processed_dir: str | Path,
    final_dir: str | Path,
    render_config: dict,
) -> List[dict]:
    _ensure_ffmpeg()

    video_path = Path(video_path)
    processed_dir = Path(processed_dir)
    final_dir = Path(final_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    rendered = []
    for highlight in highlights:
        clip_id = highlight["id"]
        safe_stem = _safe_name(f"{video_path.stem}_{clip_id}")
        processed_path = processed_dir / f"{safe_stem}_raw.mp4"
        final_path = final_dir / f"{safe_stem}_vertical.mp4"
        metadata_path = final_dir / f"{safe_stem}.json"

        cut_clip(video_path, processed_path, highlight["start"], highlight["duration"], render_config)
        render_vertical_clip(processed_path, final_path, highlight, render_config)
        metadata_path.write_text(json.dumps(highlight, indent=2), encoding="utf-8")

        rendered.append(
            {
                **highlight,
                "processed_clip": str(processed_path),
                "final_clip": str(final_path),
                "metadata": str(metadata_path),
            }
        )

    return rendered


def cut_clip(
    video_path: str | Path,
    output_path: str | Path,
    start: float,
    duration: float,
    render_config: dict | None = None,
) -> None:
    render_config = render_config or {}
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
        str(render_config.get("preset", "veryfast")),
        "-crf",
        str(render_config.get("video_crf", 23)),
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run(command)


def render_vertical_clip(
    input_path: str | Path,
    output_path: str | Path,
    highlight: dict,
    render_config: dict,
) -> None:
    filter_chain = build_vertical_filter_chain(
        hook_text=highlight.get("hook_text", "Wait for it"),
        caption_text=highlight.get("caption_text", highlight.get("summary", "")),
        width=int(render_config.get("width", 1080)),
        height=int(render_config.get("height", 1920)),
        hook_font_size=int(render_config.get("top_hook_font_size", 64)),
        caption_font_size=int(render_config.get("caption_font_size", 48)),
    )

    print(f"FFmpeg filter chain:\n{filter_chain}")

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
        str(render_config.get("preset", "veryfast")),
        "-crf",
        str(render_config.get("video_crf", 23)),
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run(command)


def get_video_duration(video_path: str | Path) -> float:
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
    result = _run(command)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def build_vertical_filter_chain(
    hook_text: str,
    caption_text: str,
    width: int,
    height: int,
    hook_font_size: int,
    caption_font_size: int,
) -> str:
    font_path = _font_file()
    filters: list[str] = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "setsar=1",
    ]

    hook_lines = _wrap_text(hook_text.upper(), max_chars=23, max_lines=2)
    caption_lines = _wrap_text(caption_text, max_chars=34, max_lines=3)

    y = 110
    for line in hook_lines:
        filters.append(_drawtext_filter(line, hook_font_size, y, font_path))
        y += hook_font_size + 22

    caption_start_y = height - 360
    for offset, line in enumerate(caption_lines):
        filters.append(
            _drawtext_filter(
                line,
                caption_font_size,
                caption_start_y + offset * (caption_font_size + 18),
                font_path,
            )
        )

    return ",".join(filters)


def _drawtext_filter(text: str, font_size: int, y: int, font_path: str) -> str:
    sanitized = _sanitize_drawtext_text(text)
    parts = ["drawtext"]

    if font_path:
        parts[0] = f"drawtext=fontfile={_escape_font_path(font_path)}"

    return (
        f"{parts[0]}:"
        f'text="{sanitized}":'
        f"fontsize={font_size}:"
        "fontcolor=white:"
        "box=1:"
        "boxcolor=black@0.6:"
        "boxborderw=18:"
        "x=(w-text_w)/2:"
        f"y={y}"
    )


def _sanitize_drawtext_text(text: str) -> str:
    cleaned = str(text).replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace('"', "'")
    cleaned = cleaned.replace(":", " ")
    cleaned = cleaned.replace(",", " ")
    cleaned = cleaned.replace("\\", " ")
    cleaned = cleaned.replace("%", " percent")
    return " ".join(cleaned.split())


def _escape_font_path(path: str) -> str:
    normalized = Path(path).as_posix()
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0]
        rest = normalized[2:]
        return f"{drive}\\:{rest}"
    return normalized.replace(":", "\\:")


def _wrap_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = _sanitize_drawtext_text(text).split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        trial = " ".join(current + [word])
        if len(trial) <= max_chars:
            current.append(word)
            continue

        if current:
            lines.append(" ".join(current))
        current = [word]
        if len(lines) == max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    return lines or ["Gameplay highlight"]


def _font_file() -> str:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def _safe_name(name: str) -> str:
    allowed = []
    for char in name.lower():
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        elif char in {" ", "."}:
            allowed.append("_")
    return "".join(allowed).strip("_") or "clip"


def _ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required but was not found on PATH.")


def _ensure_ffprobe() -> None:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required but was not found on PATH.")


def _run(command: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(command)
            + "\nSTDOUT:\n"
            + result.stdout
            + "\nSTDERR:\n"
            + result.stderr
        )
    return result
