"""Turn microclip/frame analyses into weighted highlight clip ranges."""

from __future__ import annotations

import logging
from typing import Iterable, List

from scripts.clip_timing import compute_clip_range
from scripts.ocr_utils import is_killfeed_scoring_enabled

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "ai_weight": 0.6,
    "motion_weight": 0.1,
    "audio_weight": 0.1,
    "hitmarker_bonus": 20.0,
    "killfeed_bonus": 40.0,
    "low_health_bonus": 15.0,
    "audio_spike_bonus": 10.0,
    "audio_spike_threshold": 12.0,
    "chat_spike_bonus": 15.0,
    "min_final_score": 60.0,
}


def detect_highlights(analyses: Iterable[dict], video_duration: float, config: dict) -> List[dict]:
    """Select highlight moments using weighted scoring and timestamp smoothing."""
    analyses = sorted(analyses, key=lambda item: float(item.get("timestamp", 0)))
    if not analyses:
        logger.warning("[HighlightDetector] No analyses available — cannot detect highlights.")
        return []

    weights = {**DEFAULT_WEIGHTS, **config.get("weighted_scoring", {})}
    smoothing = config.get("timestamp_smoothing", {})
    merge_seconds = float(smoothing.get("merge_seconds", config.get("merge_distance_seconds", 2)))
    max_clips = int(config.get("max_clips", 5))
    always_pick_best = bool(config.get("always_pick_best_frame", True))
    min_final_score = float(weights["min_final_score"])

    scored: list[dict] = []
    for item in analyses:
        breakdown = compute_weighted_score(item, weights)
        enriched = dict(item)
        enriched["score_breakdown"] = breakdown
        enriched["final_score"] = breakdown["final_score"]
        enriched["viral_score"] = breakdown["ai_score"]
        scored.append(enriched)
        _log_sample_scores(item, breakdown)

    ranked = sorted(scored, key=lambda item: float(item.get("final_score", 0)), reverse=True)
    candidates = [item for item in ranked if float(item.get("final_score", 0)) >= min_final_score]
    selection_mode = "weighted_threshold"

    if not candidates and always_pick_best:
        logger.warning(
            "[HighlightDetector] No samples met final score %.1f — selecting top weighted moments.",
            min_final_score,
        )
        candidates = _pick_spaced_top_samples(ranked, max_clips, merge_seconds)
        selection_mode = "weighted_fallback"

    if not candidates:
        candidates = [ranked[0]]
        selection_mode = "fallback_single"

    merged = _merge_close_candidates(candidates, merge_seconds)
    selected = sorted(merged, key=lambda item: float(item.get("final_score", 0)), reverse=True)[:max_clips]

    highlights: list[dict] = []
    for index, candidate in enumerate(sorted(selected, key=lambda item: float(item.get("timestamp", 0))), start=1):
        timestamp = float(candidate.get("timestamp", 0))
        start, end = compute_clip_range(timestamp, float(video_duration), config)

        highlights.append(
            {
                "id": f"highlight_{index:02d}",
                "timestamp": round(timestamp, 2),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "score": round(float(candidate.get("final_score", 0)), 2),
                "categories": candidate.get("categories", []),
                "summary": candidate.get("summary", "Gameplay highlight."),
                "reason": candidate.get("reason", ""),
                "scores": candidate.get("scores", {}),
                "score_breakdown": candidate.get("score_breakdown", {}),
                "source_frame": candidate.get("poster_frame_path") or candidate.get("frame_path"),
                "source_clip": candidate.get("clip_path"),
                "selection_mode": selection_mode,
                "raw_analysis": candidate,
            }
        )

    logger.info("[HighlightDetector] Accepted %s highlight(s) via %s:", len(highlights), selection_mode)
    for highlight in highlights:
        logger.info(
            "[HighlightDetector] Final highlight %s t=%.2fs score=%.2f range=%.2fs-%.2fs",
            highlight["id"],
            highlight["timestamp"],
            highlight["score"],
            highlight["start"],
            highlight["end"],
        )

    return highlights


def compute_weighted_score(analysis: dict, weights: dict | None = None) -> dict:
    """Combine AI and optional gameplay signals into a final 0–100+ score."""
    cfg = {**DEFAULT_WEIGHTS, **(weights or {})}
    signals = analysis.get("gameplay_signals") or analysis.get("signals") or {}

    ai_score = float(analysis.get("viral_score", analysis.get("ai_score", 0)))
    motion_raw = float(signals.get("motion_intensity", analysis.get("motion_score", 0)))
    audio_raw = float(signals.get("audio_spike_score", 0))
    motion_score_0_20 = min(20.0, motion_raw * 0.2)
    audio_score_0_20 = min(20.0, audio_raw)

    hitmarker = bool(signals.get("hitmarker_detected", False))
    killfeed = bool(signals.get("killfeed_ocr_match", False))
    low_health = bool(signals.get("low_health_detected", False))
    chat_spike = bool(signals.get("chat_spike_detected", False))

    bonus = 0.0
    if hitmarker:
        bonus += float(cfg["hitmarker_bonus"])
    if killfeed and is_killfeed_scoring_enabled():
        bonus += float(cfg["killfeed_bonus"])
    if low_health:
        bonus += float(cfg["low_health_bonus"])
    if chat_spike:
        bonus += float(cfg.get("chat_spike_bonus", 15))
    if audio_score_0_20 >= float(cfg.get("audio_spike_threshold", 12)):
        bonus += float(cfg.get("audio_spike_bonus", 10))

    final_score = (
        ai_score * float(cfg["ai_weight"])
        + motion_score_0_20 * float(cfg["motion_weight"])
        + audio_score_0_20 * float(cfg["audio_weight"])
        + bonus
    )

    return {
        "ai_score": round(ai_score, 2),
        "motion_component": round(motion_score_0_20, 2),
        "audio_component": round(audio_score_0_20, 2),
        "hitmarker_detected": hitmarker,
        "killfeed_ocr_match": killfeed,
        "low_health_detected": low_health,
        "chat_spike_detected": chat_spike,
        "audio_spike_bonus_applied": audio_score_0_20 >= float(cfg.get("audio_spike_threshold", 12)),
        "bonus_points": round(bonus, 2),
        "final_score": round(final_score, 2),
    }


def _log_sample_scores(item: dict, breakdown: dict) -> None:
    signals = item.get("gameplay_signals") or {}
    logger.info(
        "[HighlightDetector] t=%.2fs ai=%.1f motion=%.1f audio=%.1f hitmarker=%s killfeed=%s low_health=%s final=%.1f",
        float(item.get("timestamp", 0)),
        breakdown["ai_score"],
        breakdown["motion_component"],
        breakdown["audio_component"],
        breakdown["hitmarker_detected"],
        breakdown["killfeed_ocr_match"],
        breakdown["low_health_detected"],
        breakdown["final_score"],
    )
    if signals.get("killfeed_ocr_text"):
        logger.info("[HighlightDetector]   killfeed OCR: %s", signals["killfeed_ocr_text"])
    if signals.get("killfeed_ocr_keyword"):
        logger.info("[HighlightDetector]   killfeed keyword: %s (+40 bonus)", signals["killfeed_ocr_keyword"])


def _pick_spaced_top_samples(ranked: List[dict], max_clips: int, merge_distance: float) -> List[dict]:
    chosen: list[dict] = []
    for candidate in ranked:
        timestamp = float(candidate.get("timestamp", 0))
        if any(abs(timestamp - float(item.get("timestamp", 0))) <= merge_distance for item in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) >= max_clips:
            break
    return chosen or [ranked[0]]


def _merge_close_candidates(candidates: List[dict], merge_distance: float) -> List[dict]:
    sorted_candidates = sorted(candidates, key=lambda item: float(item.get("timestamp", 0)))
    merged: List[dict] = []

    for candidate in sorted_candidates:
        if not merged:
            merged.append(candidate)
            continue

        previous = merged[-1]
        time_gap = float(candidate.get("timestamp", 0)) - float(previous.get("timestamp", 0))
        if time_gap <= merge_distance:
            if float(candidate.get("final_score", 0)) > float(previous.get("final_score", 0)):
                merged[-1] = _combine_candidates(candidate, previous)
            else:
                merged[-1] = _combine_candidates(previous, candidate)
        else:
            merged.append(candidate)

    return merged


def _combine_candidates(primary: dict, secondary: dict) -> dict:
    categories = list(dict.fromkeys(primary.get("categories", []) + secondary.get("categories", [])))
    combined = dict(primary)
    combined["categories"] = categories
    combined["summary"] = primary.get("summary") or secondary.get("summary")
    combined["reason"] = " ".join(
        part for part in [primary.get("reason", ""), secondary.get("summary", "")] if part
    ).strip()
    return combined
