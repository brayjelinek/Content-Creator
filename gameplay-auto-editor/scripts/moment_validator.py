"""Validate gameplay moments before applying viral clip enhancements."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def merge_validation_config(config: dict | None) -> dict[str, Any]:
    cfg = dict(config or {})
    return {
        "enabled": bool(cfg.get("require_validation", True)),
        "min_validation_score": float(cfg.get("min_validation_score", 55)),
        "min_signal_count": int(cfg.get("min_signal_count", 2)),
    }


def is_validated_highlight(highlight: dict, validation_config: dict | None = None) -> bool:
    """Return True when a moment has enough AI/heuristic/gameplay signal strength."""
    cfg = merge_validation_config(validation_config)
    if not cfg["enabled"]:
        return True

    selection_mode = str(highlight.get("selection_mode", ""))
    if selection_mode.startswith("fallback"):
        return False

    breakdown = highlight.get("score_breakdown") or {}
    raw = highlight.get("raw_analysis") or {}
    signals = raw.get("gameplay_signals") or raw.get("signals") or {}

    score = float(highlight.get("score", 0))
    signal_hits = 0

    if score >= cfg["min_validation_score"]:
        signal_hits += 1
    if float(breakdown.get("ai_score", highlight.get("viral_score", 0))) >= cfg["min_validation_score"]:
        signal_hits += 1
    if float(breakdown.get("motion_component", 0)) >= 8:
        signal_hits += 1
    if float(breakdown.get("audio_component", 0)) >= 8:
        signal_hits += 1
    if breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected"):
        signal_hits += 1
    if breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match"):
        signal_hits += 1
    if breakdown.get("low_health_detected") or signals.get("low_health_detected"):
        signal_hits += 1

    validated = signal_hits >= cfg["min_signal_count"]
    if validated:
        logger.info(
            "[Enhancer] Moment validated (%s signals, score %.1f) — applying viral effects",
            signal_hits,
            score,
        )
    else:
        logger.info(
            "[Enhancer] Moment not validated (%s/%s signals) — skipping viral effects",
            signal_hits,
            cfg["min_signal_count"],
        )
    return validated


def enrich_highlight_validation(highlight: dict, validation_config: dict | None = None) -> dict:
    """Attach validation metadata to a highlight dict."""
    updated = dict(highlight)
    updated["moment_validated"] = is_validated_highlight(updated, validation_config)
    updated["validation_signals"] = _signal_summary(updated)
    return updated


def _signal_summary(highlight: dict) -> dict[str, bool]:
    breakdown = highlight.get("score_breakdown") or {}
    raw = highlight.get("raw_analysis") or {}
    signals = raw.get("gameplay_signals") or {}
    return {
        "ai_score": float(breakdown.get("ai_score", highlight.get("viral_score", 0))) >= 55,
        "motion": float(breakdown.get("motion_component", 0)) >= 8,
        "audio": float(breakdown.get("audio_component", 0)) >= 8,
        "hitmarker": bool(breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected")),
        "killfeed": bool(breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match")),
        "low_health": bool(breakdown.get("low_health_detected") or signals.get("low_health_detected")),
    }
