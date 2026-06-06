"""Shared rendering defaults for vertical short-form export."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
    "platform_preset": "generic",
    "theme": "default",
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

PLATFORM_PRESETS: dict[str, dict[str, Any]] = {
    "generic": {},
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "top_safe_zone": 250,
        "bottom_safe_zone": 350,
        "side_safe_zone": 120,
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "top_safe_zone": 240,
        "bottom_safe_zone": 320,
        "side_safe_zone": 120,
    },
    "instagram_reels": {
        "width": 1080,
        "height": 1920,
        "top_safe_zone": 260,
        "bottom_safe_zone": 340,
        "side_safe_zone": 120,
    },
}

RENDER_THEMES: dict[str, dict[str, Any]] = {
    "default": {},
    "hormozi": {
        "top_hook_font_size": 72,
        "caption_font_size": 52,
        "impact_font_size": 80,
        "text_box_color": "black@0.75",
        "text_box_border": 20,
        "hook_max_chars": 18,
    },
    "minimal": {
        "top_hook_font_size": 56,
        "caption_font_size": 44,
        "impact_font_size": 64,
        "text_box_color": "black@0.45",
        "text_box_border": 10,
        "hook_max_chars": 24,
    },
    "gen_z": {
        "top_hook_font_size": 68,
        "caption_font_size": 50,
        "impact_font_size": 78,
        "text_box_color": "black@0.7",
        "text_box_border": 16,
        "hook_max_chars": 20,
    },
}


def merge_render_config(config: dict | None) -> dict[str, Any]:
    """Return render settings with defaults, platform preset, and theme applied."""
    merged = deepcopy(DEFAULT_RENDER_CONFIG)
    bundled = _bundled_font_candidates()
    if bundled:
        merged["font_candidates"] = bundled + list(merged["font_candidates"])

    user_config = dict(config or {})
    platform_key = str(user_config.get("platform_preset", merged.get("platform_preset", "generic"))).lower()
    theme_key = str(user_config.get("theme", merged.get("theme", "default"))).lower()

    platform = PLATFORM_PRESETS.get(platform_key, {})
    theme = RENDER_THEMES.get(theme_key, {})
    merged.update(platform)
    merged.update(theme)
    merged.update(user_config)
    merged["platform_preset"] = platform_key if platform_key in PLATFORM_PRESETS else "generic"
    merged["theme"] = theme_key if theme_key in RENDER_THEMES else "default"

    if "left_right_safe_zone" in merged and "side_safe_zone" not in user_config:
        merged["side_safe_zone"] = merged["left_right_safe_zone"]

    viral = dict(merged.get("viral_enhancements") or {})
    theme_viral = dict(theme.get("viral_enhancements") or {})
    viral.update(theme_viral)
    if viral:
        merged["viral_enhancements"] = viral

    font_rel, workdir = prepare_overlay_font(merged.get("font_candidates"))
    merged["_overlay_font_rel"] = font_rel
    merged["_ffmpeg_workdir"] = str(workdir)
    return merged


def _writable_app_root() -> Path:
    """Return a writable app root (user data dir when frozen, repo root in dev)."""
    if getattr(sys, "frozen", False):
        app_dir_name = "GameplayAutoEditor"
        if sys.platform.startswith("win"):
            base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        path = base / app_dir_name
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parents[1]


def prepare_overlay_font(candidates: list[str] | None = None) -> tuple[str, Path]:
    """Copy a usable font to fonts/overlay.ttf and return a colon-free relative FFmpeg path.

    Windows FFmpeg drawtext treats ':' as a filter separator. Absolute paths like
    C:/Windows/Fonts/arial.ttf break overlay rendering with 'Could not load font C'.
    Using a project-relative path plus ffmpeg cwd avoids that entire class of failures.
    """
    source = resolve_font_path(candidates)
    if not source:
        raise FileNotFoundError(
            "No overlay font found. Install Arial/DejaVu or bundle fonts/DejaVuSans-Bold.ttf."
        )

    workdir = _writable_app_root()
    fonts_dir = workdir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    local_font = fonts_dir / "overlay.ttf"
    source_path = Path(source)

    if not local_font.exists() or local_font.stat().st_mtime < source_path.stat().st_mtime:
        shutil.copy2(source_path, local_font)
        logger.info("[Render] Prepared overlay font at %s (from %s)", local_font, source_path)

    return "fonts/overlay.ttf", workdir


def ffmpeg_workdir(settings: dict | None = None) -> Path:
    """Resolve the working directory FFmpeg should use for relative font paths."""
    if settings and settings.get("_ffmpeg_workdir"):
        return Path(str(settings["_ffmpeg_workdir"]))
    return _writable_app_root()


def overlay_font_reference(settings: dict | None = None) -> str:
    """Return the drawtext fontfile value (always colon-free)."""
    if settings and settings.get("_overlay_font_rel"):
        return str(settings["_overlay_font_rel"])
    return prepare_overlay_font((settings or {}).get("font_candidates"))[0]


def _bundled_font_candidates() -> list[str]:
    """Return font paths shipped beside the desktop app, if present."""
    candidates: list[str] = []
    search_roots = [
        Path(getattr(sys, "_MEIPASS", "")),
        Path(__file__).resolve().parents[1],
    ]
    for root in search_roots:
        if not root:
            continue
        for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial-Bold.ttf"):
            path = root / "fonts" / name
            if path.exists():
                candidates.append(path.as_posix())
    return candidates


def resolve_font_path(candidates: list[str] | None = None) -> str:
    """Pick the first available system font using forward-slash paths."""
    for candidate in candidates or FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path.as_posix()
    return ""
