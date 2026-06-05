"""Shared rendering defaults for vertical short-form export."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


# Vertical short-form target (TikTok, Reels, Shorts)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

# Safe zones keep text away from platform UI overlays
TOP_SAFE_ZONE = 250
BOTTOM_SAFE_ZONE = 300
LEFT_RIGHT_SAFE_ZONE = 120

# Drawtext styling
HOOK_FONT_SIZE = 64
CAPTION_FONT_SIZE = 48
TEXT_BOX_COLOR = "black@0.6"
TEXT_BOX_BORDER = 18

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]

DEFAULT_RENDER_CONFIG: dict[str, Any] = {
    "width": OUTPUT_WIDTH,
    "height": OUTPUT_HEIGHT,
    "video_crf": 23,
    "preset": "veryfast",
    "top_safe_zone": TOP_SAFE_ZONE,
    "bottom_safe_zone": BOTTOM_SAFE_ZONE,
    "left_right_safe_zone": LEFT_RIGHT_SAFE_ZONE,
    "top_hook_font_size": HOOK_FONT_SIZE,
    "caption_font_size": CAPTION_FONT_SIZE,
    "text_box_color": TEXT_BOX_COLOR,
    "text_box_border": TEXT_BOX_BORDER,
    "font_candidates": FONT_CANDIDATES,
    "add_hashtags": True,
    "hook_max_chars": 22,
    "hook_max_lines": 2,
    "caption_max_chars": 32,
    "caption_max_lines": 3,
}


def merge_render_config(config: dict | None) -> dict[str, Any]:
    """Return render settings with defaults applied."""
    merged = deepcopy(DEFAULT_RENDER_CONFIG)
    if config:
        merged.update(config)
    return merged


def resolve_font_path(candidates: list[str] | None = None) -> str:
    """Pick the first available system font for FFmpeg drawtext."""
    for candidate in candidates or FONT_CANDIDATES:
        if Path(candidate).exists():
            return Path(candidate).as_posix()
    return ""
