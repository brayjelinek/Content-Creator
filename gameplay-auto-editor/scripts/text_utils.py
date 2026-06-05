"""Text helpers for overlays and captions."""

from __future__ import annotations

import re


def sanitize_overlay_text(text: str) -> str:
    """Remove characters that break FFmpeg drawtext filters."""
    cleaned = str(text).replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace('"', "")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace(":", " ")
    cleaned = cleaned.replace(";", " ")
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
        current = [word[:max_chars]]
        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    return lines or ["Gameplay highlight"]


def validate_filter_chain(filter_chain: str) -> None:
    """Validate FFmpeg filter syntax expectations before execution."""
    if "drawtext=" in filter_chain and 'text="' not in filter_chain:
        raise ValueError("Drawtext filters must use double-quoted text values.")

    if re.search(r"text='", filter_chain):
        raise ValueError("Filter chain contains single-quoted drawtext values.")

    drawtext_segments = re.findall(r"drawtext=[^,]*", filter_chain)
    for segment in drawtext_segments:
        if "text='" in segment or "text=''" in segment:
            raise ValueError("Drawtext segment uses single quotes.")
        if 'text="' not in segment:
            raise ValueError(f"Drawtext segment missing double-quoted text: {segment}")

    font_paths = re.findall(r"fontfile=((?:\\:|[^:])+)", filter_chain)
    for raw_path in font_paths:
        normalized = raw_path.replace("\\:", ":")
        if "\\" in normalized:
            raise ValueError(f"Font path contains stray backslashes: {raw_path}")
        if normalized.count(":") > 1 or (
            len(normalized) > 1 and normalized[1] == ":" and normalized.count(":") > 1
        ):
            raise ValueError(f"Font path contains unescaped colon: {raw_path}")
        if "//" in normalized.replace("\\:", ":"):
            raise ValueError(f"Font path contains invalid slashes: {raw_path}")

    if re.search(r"x=max\(\d+,min\(", filter_chain):
        raise ValueError("Filter chain contains unescaped commas in drawtext x expressions.")


def looks_like_uuid(value: str) -> bool:
    """Return True when a filename stem looks like a UUID."""
    return bool(re.fullmatch(r"[0-9a-fA-F-]{32,36}", str(value)))
