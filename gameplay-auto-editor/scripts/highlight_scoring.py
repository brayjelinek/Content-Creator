"""Shared highlight threshold helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_FINAL_SCORE = 60.0


def resolve_min_final_score(highlight_config: dict | None, weights: dict | None = None) -> float:
    """Resolve the highlight acceptance threshold from config keys."""
    cfg = dict(highlight_config or {})
    scoring = {**(weights or {}), **dict(cfg.get("weighted_scoring") or {})}

    if cfg.get("min_score") is not None:
        return float(cfg["min_score"])
    if scoring.get("min_final_score") is not None:
        return float(scoring["min_final_score"])
    return DEFAULT_MIN_FINAL_SCORE


def sync_weighted_threshold(highlight_config: dict | None) -> dict[str, Any]:
    """Ensure weighted_scoring.min_final_score mirrors highlight_detection.min_score when needed."""
    cfg = dict(highlight_config or {})
    weights = dict(cfg.get("weighted_scoring") or {})
    threshold = resolve_min_final_score(cfg, weights)
    weights["min_final_score"] = threshold
    cfg["weighted_scoring"] = weights
    cfg["min_score"] = threshold
    return cfg
