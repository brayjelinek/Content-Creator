"""Generate styled ASS subtitles for optional viral caption burn-in."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from scripts.text_utils import sanitize_overlay_text, wrap_overlay_text

logger = logging.getLogger(__name__)


def build_ass_subtitle_path(
    highlight: dict,
    settings: dict,
    clip_duration: float,
    *,
    karaoke_words: list[dict] | None = None,
) -> Path | None:
    """Write a temporary ASS subtitle file for FFmpeg burn-in."""
    hook_text = sanitize_overlay_text(highlight.get("hook_text") or "Watch this...")
    caption_source = (
        highlight.get("transcript_snippet")
        or highlight.get("caption_text")
        or highlight.get("summary")
        or "Gameplay highlight"
    )
    caption_lines = highlight.get("caption_lines") or wrap_overlay_text(
        sanitize_overlay_text(str(caption_source)),
        max_chars=int(settings.get("caption_max_chars", 40)),
        max_lines=int(settings.get("caption_max_lines", 3)),
    )

    if not hook_text and not caption_lines:
        return None

    width = int(settings.get("width", 1080))
    height = int(settings.get("height", 1920))
    top_margin = int(settings.get("top_safe_zone", 250))
    bottom_margin = int(settings.get("bottom_safe_zone", 300))
    hook_size = int(settings.get("top_hook_font_size", 64))
    caption_size = int(settings.get("caption_font_size", 48))

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ass",
        prefix="gae_captions_",
        delete=False,
        encoding="utf-8",
    )
    path = Path(handle.name)
    handle.write(_ass_header(width, height, hook_size, caption_size, top_margin, bottom_margin))
    handle.write(_ass_dialogue(0.0, clip_duration, "Hook", hook_text.upper(), fade=True))

    if karaoke_words:
        karaoke_text = _build_karaoke_text(karaoke_words, clip_duration)
        if karaoke_text:
            handle.write(_ass_dialogue(0.2, clip_duration, "Caption", karaoke_text, fade=False))
        else:
            for index, line in enumerate(caption_lines):
                handle.write(_ass_dialogue(0.3 + index * 0.15, clip_duration, "Caption", line, fade=True))
    else:
        for index, line in enumerate(caption_lines):
            handle.write(_ass_dialogue(0.3 + index * 0.15, clip_duration, "Caption", line, fade=True))

    handle.close()
    logger.info("[ASS] Wrote styled subtitles: %s", path.name)
    return path


def escape_ass_filter_path(path: Path) -> str:
    """Escape an ASS path for FFmpeg subtitles filter."""
    normalized = path.resolve().as_posix()
    normalized = normalized.replace("\\", "/")
    normalized = normalized.replace(":", "\\:")
    normalized = normalized.replace("'", "\\'")
    return normalized


def _ass_header(
    width: int,
    height: int,
    hook_size: int,
    caption_size: int,
    top_margin: int,
    bottom_margin: int,
) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,hook_size,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,3,0,8,120,120,{top_margin},1
Style: Caption,DejaVu Sans,caption_size,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,3,0,2,120,120,{bottom_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".replace("hook_size", str(hook_size)).replace("caption_size", str(caption_size))


def _ass_dialogue(start: float, end: float, style: str, text: str, *, fade: bool) -> str:
    clean = _escape_ass_text(text)
    if fade:
        clean = rf"{{\fad(180,180)}}{clean}"
    return f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},{style},,0,0,0,,{clean}\n"


def _build_karaoke_text(words: list[dict], clip_duration: float) -> str:
    parts: list[str] = []
    for item in words:
        word = sanitize_overlay_text(str(item.get("word") or "")).strip()
        if not word:
            continue
        start = max(0.0, float(item.get("start", 0)))
        end = max(start + 0.05, float(item.get("end", start + 0.2)))
        if start > clip_duration:
            break
        duration_cs = max(1, int((end - start) * 100))
        parts.append(rf"{{\k{duration_cs}}}{word.upper()}")
    return " ".join(parts)


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def _escape_ass_text(text: str) -> str:
    cleaned = sanitize_overlay_text(text)
    cleaned = cleaned.replace("\n", r"\N")
    cleaned = re.sub(r"[{}]", "", cleaned)
    return cleaned
