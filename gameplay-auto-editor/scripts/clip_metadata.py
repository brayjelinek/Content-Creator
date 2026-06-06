"""Clip quality tiers and enhancement summaries for UI and run reports."""

from __future__ import annotations

from typing import Any


def quality_tier(highlight: dict) -> str:
    """Classify highlight confidence without blocking export."""
    mode = str(highlight.get("selection_mode") or "")
    if mode.startswith("fallback"):
        return "fallback"
    score = float(highlight.get("score", 0))
    min_score = float((highlight.get("score_breakdown") or {}).get("min_final_score", 60))
    if score >= min_score:
        return "validated"
    if score >= max(25.0, min_score * 0.5):
        return "review_recommended"
    return "low_confidence"


def summarize_enhancements(clip: dict) -> list[str]:
    """Return human-readable enhancement labels for UI badges."""
    badges: list[str] = []
    if clip.get("overlay_applied"):
        badges.append("Overlay captions")
    elif clip.get("viral_captions_burned"):
        badges.append("Burned captions")

    if clip.get("viral_enhanced"):
        badges.append("Viral polish")
    if clip.get("viral_slowmo_applied"):
        badges.append("Slow-mo")
    if clip.get("viral_sound_effect_applied"):
        badges.append("Impact SFX")
    if clip.get("zoom_applied"):
        badges.append("Impact zoom")
    return badges


def build_clip_report_entry(clip: dict) -> dict[str, Any]:
    """Compact per-clip metadata for run reports."""
    return {
        "id": clip.get("id"),
        "final_clip": clip.get("final_clip"),
        "score": clip.get("score"),
        "quality_tier": quality_tier(clip),
        "selection_mode": clip.get("selection_mode"),
        "start": clip.get("start"),
        "end": clip.get("end"),
        "duration": clip.get("duration"),
        "hook_text": clip.get("hook_text"),
        "impact_text": clip.get("impact_text"),
        "overlay_applied": bool(clip.get("overlay_applied")),
        "viral_enhanced": bool(clip.get("viral_enhanced")),
        "viral_slowmo_applied": bool(clip.get("viral_slowmo_applied")),
        "viral_captions_burned": bool(clip.get("viral_captions_burned")),
        "viral_sound_effect_applied": bool(clip.get("viral_sound_effect_applied")),
        "enhancements_applied": summarize_enhancements(clip),
    }
