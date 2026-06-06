"""Validate gameplay moments before applying premium viral clip effects."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def merge_validation_config(config: dict | None) -> dict[str, Any]:
    cfg = dict(config or {})
    require = bool(cfg.get("require_validation_for_effects", cfg.get("require_validation_for_slowmo", True)))
    return {
        "require_slowmo_validation": bool(
            cfg.get("require_validation_for_slowmo", cfg.get("require_validation", require))
        ),
        "require_effects_validation": require,
        "min_validation_score": float(cfg.get("min_validation_score", 45)),
        "min_signal_count": int(cfg.get("min_signal_count", 1)),
    }


def count_validation_signals(highlight: dict, cfg: dict[str, Any]) -> int:
    breakdown = highlight.get("score_breakdown") or {}
    raw = highlight.get("raw_analysis") or {}
    signals = raw.get("gameplay_signals") or raw.get("signals") or {}

    score = float(highlight.get("score", 0))
    signal_hits = 0

    if score >= cfg["min_validation_score"]:
        signal_hits += 1
    if float(breakdown.get("ai_score", highlight.get("viral_score", 0))) >= cfg["min_validation_score"]:
        signal_hits += 1
    if float(breakdown.get("motion_component", 0)) >= 6:
        signal_hits += 1
    if float(breakdown.get("audio_component", 0)) >= 6:
        signal_hits += 1
    if breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected"):
        signal_hits += 1
    if breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match"):
        signal_hits += 1
    if breakdown.get("low_health_detected") or signals.get("low_health_detected"):
        signal_hits += 1
    return signal_hits


def _is_fallback_moment(highlight: dict) -> bool:
    return str(highlight.get("selection_mode", "")).startswith("fallback")


def _passes_validation(highlight: dict, cfg: dict[str, Any]) -> bool:
    if _is_fallback_moment(highlight):
        return False
    signal_hits = count_validation_signals(highlight, cfg)
    return signal_hits >= cfg["min_signal_count"]


def is_validated_for_slowmo(highlight: dict, validation_config: dict | None = None) -> bool:
    """Return True when a moment is strong enough for pre-impact slow-mo."""
    cfg = merge_validation_config(validation_config)
    if not cfg["require_slowmo_validation"]:
        return True

    validated = _passes_validation(highlight, cfg)
    if validated:
        logger.info(
            "[Enhancer] Slow-mo validated (%s signals, score %.1f)",
            count_validation_signals(highlight, cfg),
            float(highlight.get("score", 0)),
        )
    else:
        logger.info(
            "[Enhancer] Slow-mo skipped (%s/%s signals) — applying standard polish only",
            count_validation_signals(highlight, cfg),
            cfg["min_signal_count"],
        )
    return validated


def is_validated_for_premium_effects(highlight: dict, validation_config: dict | None = None) -> bool:
    """Return True when zoom, impact text, and motion/audio emphasis may run."""
    cfg = merge_validation_config(validation_config)
    if not cfg["require_effects_validation"]:
        return not _is_fallback_moment(highlight)
    return _passes_validation(highlight, cfg)


def is_validated_highlight(highlight: dict, validation_config: dict | None = None) -> bool:
    """Backward-compatible alias for slow-mo validation."""
    return is_validated_for_slowmo(highlight, validation_config)


def enrich_highlight_validation(highlight: dict, validation_config: dict | None = None) -> dict:
    """Attach validation metadata to a highlight dict."""
    updated = dict(highlight)
    updated["moment_validated"] = is_validated_for_premium_effects(updated, validation_config)
    updated["slowmo_validated"] = is_validated_for_slowmo(updated, validation_config)
    updated["validation_signals"] = _signal_summary(updated, validation_config)
    return updated


def _signal_summary(highlight: dict, validation_config: dict | None = None) -> dict[str, bool]:
    cfg = merge_validation_config(validation_config)
    breakdown = highlight.get("score_breakdown") or {}
    raw = highlight.get("raw_analysis") or {}
    signals = raw.get("gameplay_signals") or {}
    min_score = cfg["min_validation_score"]
    return {
        "score": float(highlight.get("score", 0)) >= min_score,
        "ai_score": float(breakdown.get("ai_score", highlight.get("viral_score", 0))) >= min_score,
        "motion": float(breakdown.get("motion_component", 0)) >= 6,
        "audio": float(breakdown.get("audio_component", 0)) >= 6,
        "hitmarker": bool(breakdown.get("hitmarker_detected") or signals.get("hitmarker_detected")),
        "killfeed": bool(breakdown.get("killfeed_ocr_match") or signals.get("killfeed_ocr_match")),
        "low_health": bool(breakdown.get("low_health_detected") or signals.get("low_health_detected")),
    }
