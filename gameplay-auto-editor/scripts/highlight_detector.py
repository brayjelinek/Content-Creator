"""Turn frame-level analysis into clip ranges."""

from __future__ import annotations

import logging
from typing import Iterable, List

logger = logging.getLogger(__name__)


def detect_highlights(analyses: Iterable[dict], video_duration: float, config: dict) -> List[dict]:
    """Select and merge highlight-worthy moments from analyzed frames."""
    analyses = sorted(analyses, key=lambda item: float(item.get("timestamp", 0)))
    if not analyses:
        logger.warning("[HighlightDetector] No frame analyses available — cannot detect highlights.")
        return []

    min_score = float(config.get("min_score", 25))
    max_clips = int(config.get("max_clips", 5))
    merge_distance = float(config.get("merge_distance_seconds", 6))
    always_pick_best = bool(config.get("always_pick_best_frame", True))
    min_clip_seconds = float(config.get("min_clip_seconds", 3))
    max_clip_seconds = float(config.get("max_clip_seconds", 60))

    ranked = sorted(analyses, key=lambda item: _effective_score(item), reverse=True)
    peak_score = _effective_score(ranked[0])
    adaptive_threshold = min(min_score, max(15.0, peak_score * 0.55))

    logger.info("[HighlightDetector] Applying min_score threshold: %.2f", min_score)
    logger.info("[HighlightDetector] Adaptive threshold (relative to peak %.2f): %.2f", peak_score, adaptive_threshold)
    logger.info("[HighlightDetector] Raw frame scores:")
    for item in analyses:
        logger.info(
            "[HighlightDetector]   t=%.2fs raw=%.2f effective=%.2f categories=%s",
            float(item.get("timestamp", 0)),
            float(item.get("viral_score", 0)),
            _effective_score(item),
            item.get("categories", []),
        )

    candidates = [item for item in analyses if _effective_score(item) >= adaptive_threshold]
    selection_mode = "threshold"

    if not candidates and always_pick_best:
        logger.warning(
            "[HighlightDetector] No frames met adaptive threshold %.2f — selecting top moments by score.",
            adaptive_threshold,
        )
        candidates = _pick_spaced_top_frames(ranked, max_clips, merge_distance)
        selection_mode = "top_by_score"

    if not candidates:
        logger.warning("[HighlightDetector] No candidates found — using strongest single frame.")
        candidates = [ranked[0]]
        selection_mode = "fallback_single"

    merged = _merge_close_candidates(candidates, merge_distance)
    selected = sorted(merged, key=lambda item: _effective_score(item), reverse=True)[:max_clips]

    highlights = []
    before = float(config.get("clip_seconds_before", 4))
    after = float(config.get("clip_seconds_after", 8))

    for index, candidate in enumerate(sorted(selected, key=lambda item: float(item.get("timestamp", 0))), start=1):
        timestamp = float(candidate.get("timestamp", 0))
        start = max(0.0, timestamp - before)
        end = min(float(video_duration), timestamp + after) if video_duration > 0 else timestamp + after
        if end <= start:
            end = start + min_clip_seconds
        duration = end - start
        if duration < min_clip_seconds:
            end = min(float(video_duration) if video_duration > 0 else start + min_clip_seconds, start + min_clip_seconds)
        if duration > max_clip_seconds:
            end = start + max_clip_seconds

        highlights.append(
            {
                "id": f"highlight_{index:02d}",
                "timestamp": round(timestamp, 2),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "score": round(_effective_score(candidate), 2),
                "categories": candidate.get("categories", []),
                "summary": candidate.get("summary", "Gameplay highlight."),
                "reason": candidate.get("reason", ""),
                "scores": candidate.get("scores", {}),
                "source_frame": candidate.get("frame_path"),
                "selection_mode": selection_mode,
                "raw_analysis": candidate,
            }
        )

    logger.info("[HighlightDetector] Accepted %s highlight(s) via %s:", len(highlights), selection_mode)
    for highlight in highlights:
        logger.info(
            "[HighlightDetector]   %s t=%.2fs score=%.2f range=%.2fs-%.2fs",
            highlight["id"],
            highlight["timestamp"],
            highlight["score"],
            highlight["start"],
            highlight["end"],
        )

    return highlights


def _effective_score(item: dict) -> float:
    """Blend absolute and relative scores so heuristic batches still rank usefully."""
    raw = float(item.get("viral_score", 0))
    motion = float((item.get("signals") or {}).get("motion_score", item.get("motion_score", 0)))
    motion_boost = min(35.0, motion * 1.2)
    return round(max(raw, motion_boost), 2)


def _pick_spaced_top_frames(ranked: List[dict], max_clips: int, merge_distance: float) -> List[dict]:
    """Pick the highest-scoring frames that are spaced apart in time."""
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
            if _effective_score(candidate) > _effective_score(previous):
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
