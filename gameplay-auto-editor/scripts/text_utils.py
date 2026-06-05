"""Text helpers for overlays and captions."""

from __future__ import annotations

import re


def sanitize_overlay_text(text: str) -> str:
    """Make text safe for FFmpeg drawtext filter values."""
    cleaned = str(text).replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace('"', "'")
    cleaned = cleaned.replace(":", " ")
    cleaned = cleaned.replace(";", " ")
    cleaned = cleaned.replace(",", " ")
    cleaned = cleaned.replace("\\", " ")
    cleaned = cleaned.replace("%", " percent")
    cleaned = cleaned.replace("[", "(").replace("]", ")")
    cleaned = cleaned.replace("=", " ")
    return " ".join(cleaned.split())


def wrap_overlay_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Wrap overlay text into readable lines."""
    words = sanitize_overlay_text(text).split()
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
        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    return lines or ["Gameplay highlight"]


def looks_like_uuid(value: str) -> bool:
    """Return True when a filename stem looks like a UUID."""
    return bool(re.fullmatch(r"[0-9a-fA-F-]{32,36}", str(value)))
