"""Build sanitized local context for the embedded advisor (RAG without secrets)."""

from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.I),
    re.compile(r"sk-[a-zA-Z0-9]{10,}"),
    re.compile(r"Bearer\s+\S+", re.I),
)


def sanitize_text(text: str) -> str:
    """Redact likely secrets before sending to an LLM."""
    cleaned = str(text or "")
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def build_app_context(
    *,
    config: dict[str, Any],
    report: dict[str, Any] | None = None,
    ui_settings: dict[str, Any] | None = None,
    max_clips: int = 5,
) -> str:
    """Assemble a compact, sanitized context block for the advisor."""
    sections: list[str] = []

    rollout = dict(config.get("rollout") or {})
    optional = dict(rollout.get("optional_features") or {})
    vision = dict(config.get("vision") or {})
    highlight = dict(config.get("highlight_detection") or {})
    rendering = dict(config.get("rendering") or {})
    ocr = dict(config.get("ocr") or {})
    social = dict(config.get("social_publish") or {})
    agent = dict(config.get("embedded_agent") or {})

    sections.append("## App configuration (sanitized)")
    sections.append(f"- Vision provider: {vision.get('provider', 'heuristic')}")
    sections.append(f"- OpenAI key configured: {bool(str(vision.get('openai_api_key') or '').strip())}")
    sections.append(f"- Game profile: {highlight.get('game_profile', 'generic')}")
    sections.append(f"- Max clips: {highlight.get('max_clips', 5)}")
    sections.append(f"- Min score: {highlight.get('min_score', 60)}")
    sections.append(f"- Platform preset: {rendering.get('platform_preset', 'tiktok')}")
    sections.append(f"- Theme: {rendering.get('theme', 'default')}")
    sections.append(f"- Smart reframe: {bool((rendering.get('smart_reframe') or {}).get('enabled', False))}")
    sections.append(f"- OCR enabled: {bool(ocr.get('enabled', True))}")
    sections.append(f"- Direct publish enabled: {bool(social.get('enabled')) and bool(optional.get('direct_publish'))}")
    sections.append(f"- Embedded agent enabled: {bool(agent.get('enabled')) and bool(optional.get('embedded_agent'))}")

    if ui_settings:
        sections.append("\n## Current UI settings")
        for key, value in ui_settings.items():
            sections.append(f"- {key}: {sanitize_text(str(value))}")

    if report:
        sections.append("\n## Latest run report")
        sections.append(f"- Input: {sanitize_text(str(report.get('input_video', 'unknown')))}")
        sections.append(f"- Duration: {report.get('duration_seconds', '?')}s")
        sections.append(f"- Clips created: {report.get('clips_created', 0)}")
        sections.append(f"- Detection mode: {report.get('detection_mode', 'unknown')}")
        sections.append(f"- Used fallback: {bool(report.get('used_fallback'))}")
        sections.append(f"- Failure reason: {report.get('failure_reason') or 'none'}")
        tiers = report.get("quality_tier_counts") or {}
        if tiers:
            sections.append(f"- Quality tiers: {tiers}")
        features = report.get("features_applied") or {}
        active = [name for name, on in features.items() if on]
        if active:
            sections.append(f"- Active features: {', '.join(active)}")

        clips = list(report.get("clips") or report.get("clip_summaries") or [])[:max_clips]
        if clips:
            sections.append("\n## Clip details")
            for index, clip in enumerate(clips, start=1):
                sections.append(_format_clip_summary(index, clip))

    return sanitize_text("\n".join(sections))


def _format_clip_summary(index: int, clip: dict[str, Any]) -> str:
    categories = ", ".join(clip.get("categories") or []) or "none"
    badges = ", ".join(clip.get("enhancement_badges") or clip.get("badges") or []) or "none"
    return (
        f"Clip {index}: score={clip.get('score', '?')}, tier={clip.get('quality_tier', '?')}, "
        f"hook=\"{clip.get('hook_text', '')}\", categories=[{categories}], "
        f"selection={clip.get('selection_mode', 'normal')}, enhancements=[{badges}]"
    )


def build_setup_help() -> str:
    """Static setup guidance when no LLM is available."""
    return sanitize_text(
        "## Setup checklist\n"
        "1. FFmpeg must be on PATH for clip rendering.\n"
        "2. Optional: install Tesseract for killfeed OCR.\n"
        "3. Optional: add OPENAI_API_KEY to .env for AI vision and the assistant.\n"
        "4. Optional: enable embedded_agent in config.json + rollout.optional_features.embedded_agent.\n"
        "5. Optional: add OAuth credentials in .env for direct platform posting.\n"
        "6. Game profiles (valorant, cod, fortnite) improve detection accuracy.\n"
    )
