"""Turn frame-level analysis into clip ranges."""

from __future__ import annotations

from typing import Iterable, List


def detect_highlights(analyses: Iterable[dict], video_duration: float, config: dict) -> List[dict]:
    """Select and merge highlight-worthy moments from analyzed frames."""
    analyses = sorted(analyses, key=lambda item: float(item.get("timestamp", 0)))
    if not analyses:
        return []

    min_score = float(config.get("min_score", 55))
    max_clips = int(config.get("max_clips", 5))
    merge_distance = float(config.get("merge_distance_seconds", 6))

    candidates = [item for item in analyses if float(item.get("viral_score", 0)) >= min_score]
    if not candidates:
        candidates = [max(analyses, key=lambda item: float(item.get("viral_score", 0)))]
        candidates[0]["reason"] = (
            candidates[0].get("reason", "")
            + " Selected as the strongest available moment because no frame met min_score."
        ).strip()

    merged = _merge_close_candidates(candidates, merge_distance)
    ranked = sorted(merged, key=lambda item: float(item.get("viral_score", 0)), reverse=True)[:max_clips]

    highlights = []
    before = float(config.get("clip_seconds_before", 4))
    after = float(config.get("clip_seconds_after", 8))

    for index, candidate in enumerate(sorted(ranked, key=lambda item: float(item.get("timestamp", 0))), start=1):
        timestamp = float(candidate.get("timestamp", 0))
        start = max(0.0, timestamp - before)
        end = min(float(video_duration), timestamp + after) if video_duration else timestamp + after
        if end <= start:
            end = start + 1.0

        highlights.append(
            {
                "id": f"highlight_{index:02d}",
                "timestamp": round(timestamp, 2),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "score": round(float(candidate.get("viral_score", 0)), 2),
                "categories": candidate.get("categories", []),
                "summary": candidate.get("summary", "Gameplay highlight."),
                "reason": candidate.get("reason", ""),
                "scores": candidate.get("scores", {}),
                "source_frame": candidate.get("frame_path"),
                "raw_analysis": candidate,
            }
        )

    return highlights


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
            if float(candidate.get("viral_score", 0)) > float(previous.get("viral_score", 0)):
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
