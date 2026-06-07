"""Generate hook and caption text optimized for vertical short-form overlays."""

from __future__ import annotations

import random
from typing import Iterable, List

from scripts.text_utils import looks_like_uuid, sanitize_overlay_text, wrap_overlay_text

GENERIC_SUMMARIES = frozenset(
    {
        "high-action microclip with strong gameplay signals",
        "lower-intensity gameplay microclip",
        "gameplay highlight",
    }
)


def _normalize_summary(summary: str) -> str:
    return sanitize_overlay_text(summary).strip().lower().rstrip(".")

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

PROFILE_HOOKS: dict[str, dict[str, tuple[str, ...]]] = {
    "generic": {
        "kills": ("Clean pick", "That was nasty", "They never saw it"),
        "clutch plays": ("Clutch or throw", "No way he survived", "Last second save"),
        "fails": ("Instant regret", "How did I miss", "Throw of the day"),
    },
    "valorant": {
        "kills": ("Headshot confirmed", "Ace incoming?", "One tap city"),
        "clutch plays": ("1v5? Hold my spike", "Clutch with no HP", "Round stolen"),
    },
    "cod": {
        "kills": ("Squad wipe energy", "Beam city", "They got cooked"),
        "clutch plays": ("Clutch on one bar", "Last kill saves it", "Search and destroy"),
    },
    "fortnite": {
        "kills": ("Box fight won", "Third party chaos", "Cracked and stacked"),
        "clutch plays": ("Victory royale path", "Clutch build fight", "Last player standing"),
    },
}

VIRAL_HOOKS = (
    "Watch this...",
    "No way this happened",
    "Insane moment",
    "This was wild",
)

THEME_HOOKS = {
    "hormozi": ("THIS CHANGES EVERYTHING", "YOU NEED TO SEE THIS", "STOP SCROLLING"),
    "minimal": ("Highlight", "Key moment", "Watch closely"),
    "gen_z": ("NO WAY 💀", "BRO WHAT", "THIS IS CRAZY"),
}

THEME_IMPACTS = {
    "hormozi": ("INSANE", "GAME OVER", "CLUTCH"),
    "minimal": ("Nice", "Clean", "Sharp"),
    "gen_z": ("WTF", "NO WAY", "RIP"),
}

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
    game_profile: str = "generic",
) -> List[dict]:
    """Attach overlay-safe hook and wrapped caption lines to each highlight."""
    from scripts.render_settings import merge_render_config

    settings = merge_render_config(render_config)
    theme = str(settings.get("theme", "default")).lower()
    caption_max_chars = int(settings.get("caption_max_chars", 40))
    caption_max_lines = int(settings.get("caption_max_lines", 3))
    overlay_hashtags = bool(settings.get("add_hashtags_to_overlay", False))
    display_name = _display_video_name(video_name)
    profile_id = str(game_profile or "generic").lower()
    used_hooks: set[str] = set()
    captioned = []

    for highlight in highlights:
        categories = [str(category) for category in highlight.get("categories", [])]
        score = float(highlight.get("score", 0))
        hook = sanitize_overlay_text(
            _pick_unique_hook(categories, score, highlight, theme, profile_id, used_hooks)
        )
        impact_text = sanitize_overlay_text(_pick_impact_text(highlight, categories, theme))
        overlay_body = sanitize_overlay_text(_overlay_caption_text(highlight, score))
        social_body = sanitize_overlay_text(_social_caption_text(highlight, display_name, score, hook))

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


def _gameplay_signals(highlight: dict) -> dict:
    raw = highlight.get("raw_analysis") or {}
    return dict(raw.get("gameplay_signals") or {})


def _signal_driven_hook(highlight: dict, profile_id: str) -> str | None:
    """Build a moment-specific hook from HUD signals or vision summary."""
    signals = _gameplay_signals(highlight)
    breakdown = highlight.get("score_breakdown") or {}

    killfeed = str(signals.get("killfeed_ocr_keyword") or "").strip()
    if killfeed:
        title = killfeed.title()
        lowered = killfeed.lower()
        if "headshot" in lowered:
            return "Headshot confirmed"
        if "ace" in lowered:
            return "Ace round incoming"
        if "double" in lowered:
            return "Double kill chaos"
        if "clutch" in lowered:
            return "Clutch play locked"
        return f"{title[:16]} moment"

    if breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match"):
        return "Killfeed confirms it"
    if breakdown.get("low_health_detected") or signals.get("low_health_detected"):
        return "1 HP clutch play"
    if breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected"):
        return "Hitmarker goes crazy"
    if signals.get("chat_spike_detected"):
        return "Chat lost their minds"
    if float(signals.get("audio_spike_score") or 0) >= 14:
        return "Listen to that peak"

    summary = sanitize_overlay_text(str(highlight.get("summary") or "")).strip()
    summary_key = _normalize_summary(summary)
    if summary and summary_key not in GENERIC_SUMMARIES:
        if len(summary) <= 22:
            return summary
        sentence = summary.split(".")[0].strip()
        if 8 <= len(sentence) <= 22:
            return sentence
        if len(sentence) > 22:
            return sentence[:22].rstrip()

    return None


def _profile_hook(categories: list[str], profile_id: str, highlight: dict) -> str | None:
    profile_hooks = PROFILE_HOOKS.get(profile_id) or PROFILE_HOOKS["generic"]
    rng = random.Random(int(float(highlight.get("timestamp", 0)) * 1000))
    for category in categories:
        options = profile_hooks.get(category.lower()) or PROFILE_HOOKS["generic"].get(category.lower())
        if options:
            return rng.choice(options)
    return None


def _pick_hook(
    categories: list[str],
    score: float,
    highlight: dict,
    theme: str = "default",
    profile_id: str = "generic",
) -> str:
    custom_hook = str(highlight.get("custom_hook_text") or "").strip()
    if custom_hook:
        return custom_hook

    signal_hook = _signal_driven_hook(highlight, profile_id)
    if signal_hook:
        return signal_hook

    profile_hook = _profile_hook(categories, profile_id, highlight)
    if profile_hook and score >= 45:
        return profile_hook

    rng = random.Random(int(float(highlight.get("timestamp", 0)) * 1000) + int(score))
    theme_hooks = THEME_HOOKS.get(theme)
    if theme_hooks and rng.random() >= 0.55:
        return rng.choice(theme_hooks)

    for category in categories:
        normalized = category.lower()
        if normalized in CATEGORY_HOOKS and normalized != "setup moment":
            pool = (CATEGORY_HOOKS[normalized],)
            if profile_id in PROFILE_HOOKS and normalized in PROFILE_HOOKS[profile_id]:
                pool = PROFILE_HOOKS[profile_id][normalized]
            return rng.choice(pool)

    if score >= 80:
        return "This clip is wild"
    if score >= 65:
        return "Underrated gameplay moment"
    return rng.choice(VIRAL_HOOKS)


def _pick_unique_hook(
    categories: list[str],
    score: float,
    highlight: dict,
    theme: str,
    profile_id: str,
    used_hooks: set[str],
) -> str:
    base_rng = random.Random(int(float(highlight.get("timestamp", 0)) * 1000) + int(score) + 91)
    hook = _pick_hook(categories, score, highlight, theme, profile_id)
    normalized = hook.lower().strip()
    if normalized not in used_hooks:
        used_hooks.add(normalized)
        return hook

    for suffix in ("+", "!!", " 👀", " fr"):
        candidate = sanitize_overlay_text(f"{hook[: max(1, 22 - len(suffix))]}{suffix}")
        key = candidate.lower()
        if key not in used_hooks:
            used_hooks.add(key)
            return candidate

    for attempt in range(6):
        alt_score = score + base_rng.randint(1, 9) + attempt
        alt = _pick_hook(categories, alt_score, highlight, theme, profile_id)
        key = alt.lower().strip()
        if key not in used_hooks:
            used_hooks.add(key)
            return alt

    used_hooks.add(normalized)
    return hook


def _pick_impact_text(highlight: dict, categories: list[str], theme: str = "default") -> str:
    custom_impact = str(highlight.get("custom_impact_text") or "").strip()
    if custom_impact:
        return custom_impact.upper()

    theme_impacts = THEME_IMPACTS.get(theme)
    signals = _gameplay_signals(highlight)
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

    ai_score = float(breakdown.get("ai_score", highlight.get("viral_score", 0)))
    if ai_score >= 75 and any(cat.lower() in {"kills", "clutch plays", "high-action sequences"} for cat in categories):
        return rng.choice(("INSANE", "CLUTCH", "HEADSHOT"))

    for category in categories:
        options = IMPACT_BY_CATEGORY.get(category.lower())
        if options:
            return rng.choice(options)

    if theme_impacts:
        return rng.choice(theme_impacts)

    return rng.choice(DEFAULT_IMPACT_TEXTS)


def _signal_caption_body(highlight: dict) -> str | None:
    signals = _gameplay_signals(highlight)
    breakdown = highlight.get("score_breakdown") or {}
    parts: list[str] = []

    killfeed = str(signals.get("killfeed_ocr_keyword") or "").strip()
    if killfeed:
        parts.append(f"Killfeed: {killfeed.title()}")
    elif breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match"):
        parts.append("Kill confirmed on feed")

    if breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected"):
        parts.append("Hitmarker flash on target")
    if breakdown.get("low_health_detected") or signals.get("low_health_detected"):
        parts.append("Clutch pressure at low health")
    if signals.get("chat_spike_detected"):
        parts.append("Chat spiked right here")
    audio_score = float(signals.get("audio_spike_score") or 0)
    if audio_score >= 12:
        parts.append("Audio peak in the action")

    if not parts:
        return None
    return ". ".join(parts)[:120].rstrip(".")


def _overlay_caption_text(highlight: dict, score: float) -> str:
    """Short on-screen caption optimized for 40-char line wrapping."""
    transcript = sanitize_overlay_text(str(highlight.get("transcript_snippet") or "")).strip()
    if transcript:
        return transcript[:120].rstrip()

    signal_body = _signal_caption_body(highlight)
    if signal_body:
        return signal_body

    summary = sanitize_overlay_text(str(highlight.get("summary") or "Gameplay highlight"))
    summary = summary.rstrip(".")
    if _normalize_summary(summary) not in GENERIC_SUMMARIES:
        if len(summary) > 72:
            summary = summary[:69].rstrip() + "..."
        return summary

    categories = [str(c).lower() for c in highlight.get("categories") or []]
    if "clutch plays" in categories:
        return "Clutch moment under pressure"
    if "kills" in categories:
        return "Clean elimination in the fight"
    if score >= 60:
        return "High-intensity play from this run"
    return "Key moment from this gameplay"


def _social_caption_text(highlight: dict, video_name: str, score: float, hook: str) -> str:
    """Longer caption for export/sharing metadata, not burned into video."""
    body = sanitize_overlay_text(
        str(highlight.get("caption_text") or highlight.get("summary") or "Gameplay highlight")
    ).rstrip(".")
    categories = highlight.get("categories") or []
    label = str(categories[0]).title() if categories else "Highlight"
    if video_name and video_name != "this gameplay session":
        return f"{hook}. {label}: {body[:90]}. From {video_name}."
    return f"{hook}. {label}: {body[:100]}."


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
