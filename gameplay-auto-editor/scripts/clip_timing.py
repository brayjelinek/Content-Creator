"""Shared clip window calculation with adaptive padding and minimum duration."""

from __future__ import annotations


def compute_clip_range(
    timestamp: float,
    video_duration: float,
    config: dict | None = None,
) -> tuple[float, float]:
    """Return start/end seconds for a highlight clip, enforcing minimum length."""
    cfg = dict(config or {})
    smoothing = cfg.get("timestamp_smoothing", {})

    before = float(cfg.get("clip_seconds_before", 2.0))
    after = float(cfg.get("clip_seconds_after", 3.0))
    start_padding = float(smoothing.get("start_padding", 1.5))
    end_padding = float(smoothing.get("end_padding", 2.5))
    min_clip_seconds = float(cfg.get("min_clip_seconds", 5))
    max_clip_seconds = float(cfg.get("max_clip_seconds", 60))
    duration_floor = float(cfg.get("duration_floor_seconds", min_clip_seconds))
    min_target = max(min_clip_seconds, duration_floor)

    if cfg.get("adaptive_padding_enabled", True) and video_duration > 0:
        before, after, start_padding, end_padding = _adapt_padding(
            video_duration=video_duration,
            before=before,
            after=after,
            start_padding=start_padding,
            end_padding=end_padding,
            short_video_threshold=float(cfg.get("adaptive_short_video_threshold", 30)),
        )

    start = max(0.0, timestamp - before - start_padding)
    if video_duration > 0:
        end = min(float(video_duration), timestamp + after + end_padding)
    else:
        end = timestamp + after + end_padding

    if end <= start:
        end = start + min_target

    start, end = _expand_to_minimum(
        start=start,
        end=end,
        timestamp=timestamp,
        min_seconds=min_target,
        video_duration=video_duration,
    )

    if end - start > max_clip_seconds:
        half = max_clip_seconds / 2
        start = max(0.0, timestamp - half)
        end = start + max_clip_seconds
        if video_duration > 0:
            end = min(float(video_duration), end)
            start = max(0.0, end - max_clip_seconds)

    return round(start, 2), round(end, 2)


def _adapt_padding(
    *,
    video_duration: float,
    before: float,
    after: float,
    start_padding: float,
    end_padding: float,
    short_video_threshold: float,
) -> tuple[float, float, float, float]:
    """Scale padding down on short sources so clips still fit without feeling like trims."""
    if video_duration >= short_video_threshold:
        return before, after, start_padding, end_padding

    ratio = max(0.35, min(1.0, video_duration / short_video_threshold))
    return (
        max(0.75, before * ratio),
        max(1.0, after * ratio),
        max(0.5, start_padding * ratio),
        max(0.75, end_padding * ratio),
    )


def _expand_to_minimum(
    *,
    start: float,
    end: float,
    timestamp: float,
    min_seconds: float,
    video_duration: float,
) -> tuple[float, float]:
    """Expand clip boundaries symmetrically until minimum duration is met."""
    if end - start >= min_seconds:
        return start, end

    if video_duration > 0 and video_duration <= min_seconds:
        return 0.0, float(video_duration)

    deficit = min_seconds - (end - start)
    expand_after = deficit / 2
    expand_before = deficit - expand_after

    new_start = max(0.0, start - expand_before)
    new_end = end + expand_after
    if video_duration > 0:
        new_end = min(float(video_duration), new_end)

    if new_end - new_start < min_seconds:
        remaining = min_seconds - (new_end - new_start)
        new_start = max(0.0, new_start - remaining)
        if video_duration > 0:
            new_end = min(float(video_duration), new_start + min_seconds)
            new_start = max(0.0, new_end - min_seconds)

    if new_end - new_start < min_seconds and video_duration > 0:
        center = max(0.0, min(timestamp, float(video_duration)))
        half = min(min_seconds / 2, float(video_duration) / 2)
        new_start = max(0.0, center - half)
        new_end = min(float(video_duration), new_start + min_seconds)
        new_start = max(0.0, new_end - min_seconds)

    return new_start, new_end
