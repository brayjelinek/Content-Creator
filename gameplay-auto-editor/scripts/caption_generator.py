"""Generate hook and caption text optimized for vertical short-form overlays."""

from __future__ import annotations

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
}

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
    display_name = _display_video_name(video_name)
    captioned = []

    for highlight in highlights:
        categories = [str(category) for category in highlight.get("categories", [])]
        score = float(highlight.get("score", 0))
        hook = sanitize_overlay_text(_pick_hook(categories, score))
        caption_body = sanitize_overlay_text(_caption_text(highlight, display_name, score))

        if add_hashtags:
            caption_body = sanitize_overlay_text(f"{caption_body} {DEFAULT_HASHTAGS}")

        caption_lines = wrap_overlay_text(
            caption_body,
            max_chars=caption_max_chars,
            max_lines=caption_max_lines,
        )

        updated = dict(highlight)
        updated["hook_text"] = hook
        updated["caption_text"] = " ".join(caption_lines)
        updated["caption_lines"] = caption_lines
        updated["short_title"] = sanitize_overlay_text(_short_title(categories, hook))
        captioned.append(updated)

    return captioned


def _pick_hook(categories: list[str], score: float) -> str:
    for category in categories:
        normalized = category.lower()
        if normalized in CATEGORY_HOOKS:
            return CATEGORY_HOOKS[normalized]

    if score >= 80:
        return "This clip is wild"
    if score >= 65:
        return "Underrated gameplay moment"
    return "Wait for it"


def _caption_text(highlight: dict, video_name: str, score: float) -> str:
    summary = sanitize_overlay_text(str(highlight.get("summary") or "Gameplay highlight"))
    summary = summary.rstrip(".")
    score_int = int(round(score))

    if video_name:
        return f"{summary}. Viral score {score_int} out of 100 from {video_name}."
    return f"{summary}. Viral score {score_int} out of 100."


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
