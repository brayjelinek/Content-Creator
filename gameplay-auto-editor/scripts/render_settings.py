"""Shared rendering defaults for vertical short-form export."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

TOP_SAFE_ZONE = 250
BOTTOM_SAFE_ZONE = 300
SIDE_SAFE_ZONE = 120

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
    "side_safe_zone": SIDE_SAFE_ZONE,
    "top_hook_font_size": HOOK_FONT_SIZE,
    "caption_font_size": CAPTION_FONT_SIZE,
    "text_box_color": TEXT_BOX_COLOR,
    "text_box_border": TEXT_BOX_BORDER,
    "font_candidates": FONT_CANDIDATES,
    "add_hashtags": True,
    "hook_max_chars": 22,
    "hook_max_lines": 2,
    "caption_max_chars": 40,
    "caption_max_lines": 3,
    "add_hashtags_to_overlay": False,
}


def merge_render_config(config: dict | None) -> dict[str, Any]:
    """Return render settings with defaults applied."""
    merged = deepcopy(DEFAULT_RENDER_CONFIG)
    if config:
        merged.update(config)
        if "left_right_safe_zone" in config and "side_safe_zone" not in config:
            merged["side_safe_zone"] = config["left_right_safe_zone"]
    return merged


def resolve_font_path(candidates: list[str] | None = None) -> str:
    """Pick the first available system font using forward-slash paths."""
    for candidate in candidates or FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path.as_posix()
    return ""
