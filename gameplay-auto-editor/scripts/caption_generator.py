"""Generate simple hook and caption text for selected clips."""

from __future__ import annotations

from typing import Iterable, List


CATEGORY_HOOKS = {
    "kills": "Clean elimination!",
    "deaths": "I did not see that coming",
    "clutch plays": "Clutch or panic?",
    "explosions": "Everything exploded",
    "funny moments": "This went off-script",
    "fails": "Instant regret",
    "high-action sequences": "Blink and you miss it",
    "fast movement or chaos": "Pure chaos",
    "emotional reactions": "The reaction says it all",
}


def generate_captions(highlights: Iterable[dict], video_name: str, add_hashtags: bool = True) -> List[dict]:
    captioned = []
    for highlight in highlights:
        categories = [str(category) for category in highlight.get("categories", [])]
        hook = _pick_hook(categories, float(highlight.get("score", 0)))
        caption = _caption_text(highlight, video_name)
        if add_hashtags:
            caption = f"{caption} #gaming #highlights #clips"

        updated = dict(highlight)
        updated["hook_text"] = hook
        updated["caption_text"] = caption
        updated["short_title"] = _short_title(categories, hook)
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


def _caption_text(highlight: dict, video_name: str) -> str:
    summary = str(highlight.get("summary") or "Gameplay highlight.").rstrip(".")
    score = int(round(float(highlight.get("score", 0))))
    return f"{summary}. Viral score: {score}/100 from {video_name}."


def _short_title(categories: list[str], hook: str) -> str:
    if categories:
        return f"{hook} - {categories[0].title()}"
    return hook
