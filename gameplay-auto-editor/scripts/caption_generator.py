"""Generate hook and caption text optimized for vertical short-form overlays."""

from __future__ import annotations

import random
from typing import Iterable, List

from scripts.text_utils import looks_like_uuid, sanitize_overlay_text, wrap_overlay_text


CATEGORY_HOOKS = {
    "kills": "Clean elimination",
    "deaths": "I did not see that coming",
    "clutch plays": "Clutch or panic",
    "explosions": "Everything exploded",
    "funny moments": "This went off script",
    "fails": "Instant regret",
    "high-action sequences": "Blink and you miss it",
    "fast movement or chaos": "Pure chaos",
    "emotional reactions": "The reaction says it all",
    "setup moment": "Wait for it",
}

VIRAL_HOOKS = (
    "Watch this...",
    "No way this happened",
    "Insane moment",
    "This was wild",
)

IMPACT_BY_CATEGORY = {
    "kills": ("HEADSHOT", "ELIMINATED", "INSANE"),
    "deaths": ("NO WAY", "RIP", "INSTANT"),
    "clutch plays": ("CLUTCH", "INSANE", "NO WAY"),
    "explosions": ("BOOM", "INSANE", "WILD"),
    "funny moments": ("LOL", "NO WAY", "WILD"),
    "fails": ("FAIL", "NO WAY", "RIP"),
    "high-action sequences": ("INSANE", "CHAOS", "WILD"),
    "fast movement or chaos": ("CHAOS", "INSANE", "WILD"),
}

DEFAULT_IMPACT_TEXTS = ("INSANE", "CLUTCH", "NO WAY", "HEADSHOT", "DOUBLE KILL")

DEFAULT_HASHTAGS = "#gaming #highlights #shorts #clips"


def generate_captions(
    highlights: Iterable[dict],
    video_name: str,
    add_hashtags: bool = True,
    render_config: dict | None = None,
) -> List[dict]:
    """Attach overlay-safe hook and wrapped caption lines to each highlight."""
    from scripts.render_settings import merge_render_config

    settings = merge_render_config(render_config)
    caption_max_chars = int(settings.get("caption_max_chars", 40))
    caption_max_lines = int(settings.get("caption_max_lines", 3))
    overlay_hashtags = bool(settings.get("add_hashtags_to_overlay", False))
    display_name = _display_video_name(video_name)
    captioned = []

    for highlight in highlights:
        categories = [str(category) for category in highlight.get("categories", [])]
        score = float(highlight.get("score", 0))
        hook = sanitize_overlay_text(_pick_hook(categories, score, highlight))
        impact_text = sanitize_overlay_text(_pick_impact_text(highlight, categories))
        overlay_body = sanitize_overlay_text(_overlay_caption_text(highlight, score))
        social_body = sanitize_overlay_text(_social_caption_text(highlight, display_name, score))

        if add_hashtags:
            social_body = sanitize_overlay_text(f"{social_body} {DEFAULT_HASHTAGS}")
        if overlay_hashtags:
            overlay_body = sanitize_overlay_text(f"{overlay_body} {DEFAULT_HASHTAGS}")

        caption_lines = wrap_overlay_text(
            overlay_body,
            max_chars=caption_max_chars,
            max_lines=caption_max_lines,
        )

        updated = dict(highlight)
        updated["hook_text"] = hook
        updated["impact_text"] = impact_text
        updated["caption_text"] = " ".join(caption_lines)
        updated["caption_lines"] = caption_lines
        updated["social_caption"] = social_body
        updated["short_title"] = sanitize_overlay_text(_short_title(categories, hook))
        captioned.append(updated)

    return captioned


def _pick_hook(categories: list[str], score: float, highlight: dict) -> str:
    custom_hook = str(highlight.get("custom_hook_text") or "").strip()
    if custom_hook:
        return custom_hook

    rng = random.Random(int(float(highlight.get("timestamp", 0)) * 1000) + int(score))
    if score >= 60 or not categories or categories == ["setup moment"]:
        if rng.random() >= 0.35:
            return rng.choice(VIRAL_HOOKS)

    for category in categories:
        normalized = category.lower()
        if normalized in CATEGORY_HOOKS:
            return CATEGORY_HOOKS[normalized]

    if score >= 80:
        return "This clip is wild"
    if score >= 65:
        return "Underrated gameplay moment"
    return rng.choice(VIRAL_HOOKS)


def _pick_impact_text(highlight: dict, categories: list[str]) -> str:
    custom_impact = str(highlight.get("custom_impact_text") or "").strip()
    if custom_impact:
        return custom_impact.upper()

    raw = highlight.get("raw_analysis") or {}
    signals = raw.get("gameplay_signals") or {}
    breakdown = highlight.get("score_breakdown") or {}
    rng = random.Random(int(float(highlight.get("timestamp", 0)) * 1000) + 17)

    killfeed_keyword = signals.get("killfeed_ocr_keyword") or ""
    if killfeed_keyword:
        keyword = str(killfeed_keyword).upper()
        if "double" in keyword.lower():
            return "DOUBLE KILL"
        if "headshot" in keyword.lower():
            return "HEADSHOT"
        return keyword[:18]

    if breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match"):
        return "DOUBLE KILL"
    if breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected"):
        return "HEADSHOT"
    if breakdown.get("low_health_detected") or signals.get("low_health_detected"):
        return "CLUTCH"

    for category in categories:
        options = IMPACT_BY_CATEGORY.get(category.lower())
        if options:
            return rng.choice(options)

    return rng.choice(DEFAULT_IMPACT_TEXTS)


def _overlay_caption_text(highlight: dict, score: float) -> str:
    """Short on-screen caption optimized for 40-char line wrapping."""
    summary = sanitize_overlay_text(str(highlight.get("summary") or "Gameplay highlight"))
    summary = summary.rstrip(".")
    if len(summary) > 72:
        summary = summary[:69].rstrip() + "..."
    return summary


def _social_caption_text(highlight: dict, video_name: str, score: float) -> str:
    """Longer caption for export/sharing metadata, not burned into video."""
    summary = sanitize_overlay_text(str(highlight.get("summary") or "Gameplay highlight"))
    summary = summary.rstrip(".")
    score_int = int(round(score))
    if video_name:
        return f"{summary}. Viral score {score_int}/100 from {video_name}."
    return f"{summary}. Viral score {score_int}/100."


def _short_title(categories: list[str], hook: str) -> str:
    if categories:
        return f"{hook} - {categories[0].title()}"
    return hook


def _display_video_name(video_name: str) -> str:
    """Avoid showing UUID-like filenames in on-screen captions."""
    cleaned = sanitize_overlay_text(video_name.replace("_", " "))
    if looks_like_uuid(video_name) or len(cleaned) > 24:
        return "this gameplay session"
    return cleaned
