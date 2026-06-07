"""Time-ordered kill streak bonuses for highlight scoring."""

from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

DEFAULT_STREAK_CONFIG = {
    "enabled": True,
    "window_seconds": 8.0,
    "bonus_per_kill": 12.0,
    "multi_kill_bonus": 20.0,
    "max_bonus": 45.0,
}


def apply_streak_bonuses(analyses: Iterable[dict], config: dict | None = None) -> list[dict]:
    """Boost scores when OCR/time-ordered samples show multi-kill continuity."""
    cfg = {**DEFAULT_STREAK_CONFIG, **dict(config or {})}
    if not cfg.get("enabled", True):
        return list(analyses)

    ordered = sorted(analyses, key=lambda item: float(item.get("timestamp", 0)))
    window = max(float(cfg.get("window_seconds", 8.0)), 1.0)
    bonus_per_kill = float(cfg.get("bonus_per_kill", 12.0))
    multi_kill_bonus = float(cfg.get("multi_kill_bonus", 20.0))
    max_bonus = float(cfg.get("max_bonus", 45.0))

    kill_timestamps: list[float] = []
    for item in ordered:
        signals = item.get("gameplay_signals") or item.get("signals") or {}
        if signals.get("killfeed_ocr_match"):
            kill_timestamps.append(float(item.get("timestamp", 0)))

    enriched: list[dict] = []
    for item in ordered:
        updated = dict(item)
        breakdown = dict(updated.get("score_breakdown") or {})
        timestamp = float(updated.get("timestamp", 0))
        streak_bonus = _streak_bonus_for_timestamp(
            timestamp=timestamp,
            kill_timestamps=kill_timestamps,
            window=window,
            bonus_per_kill=bonus_per_kill,
            multi_kill_bonus=multi_kill_bonus,
            max_bonus=max_bonus,
            signals=updated.get("gameplay_signals") or updated.get("signals") or {},
        )
        if streak_bonus > 0:
            breakdown["streak_bonus"] = round(streak_bonus, 2)
            breakdown["streak_kills_in_window"] = _kills_in_window(timestamp, kill_timestamps, window)
            final_score = float(breakdown.get("final_score", updated.get("final_score", 0))) + streak_bonus
            breakdown["final_score"] = round(final_score, 2)
            updated["final_score"] = breakdown["final_score"]
            updated["score"] = breakdown["final_score"]
        updated["score_breakdown"] = breakdown
        enriched.append(updated)

    boosted = sum(1 for item in enriched if (item.get("score_breakdown") or {}).get("streak_bonus"))
    if boosted:
        logger.info("[StreakScoring] Applied streak bonus to %s sample(s)", boosted)
    return enriched


def _kills_in_window(timestamp: float, kill_timestamps: list[float], window: float) -> int:
    lower = timestamp - window
    upper = timestamp + window
    return sum(1 for value in kill_timestamps if lower <= value <= upper)


def _streak_bonus_for_timestamp(
    *,
    timestamp: float,
    kill_timestamps: list[float],
    window: float,
    bonus_per_kill: float,
    multi_kill_bonus: float,
    max_bonus: float,
    signals: dict,
) -> float:
    if not kill_timestamps:
        return 0.0

    nearby = _kills_in_window(timestamp, kill_timestamps, window)
    if nearby < 2:
        return 0.0

    bonus = bonus_per_kill * max(nearby - 1, 0)
    keyword = str(signals.get("killfeed_ocr_keyword") or "").lower()
    if any(token in keyword for token in ("double", "triple", "quad", "multi", "squad wipe")):
        bonus += multi_kill_bonus

    return min(max_bonus, bonus)
