"""Adaptive microclip sampling around motion/audio peaks."""

from __future__ import annotations

import logging
from typing import Iterable

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_ADAPTIVE_CONFIG = {
    "enabled": False,
    "coarse_interval_seconds": 2.0,
    "dense_interval_seconds": 0.5,
    "peak_window_seconds": 3.0,
    "peak_count": 5,
    "coarse_max_samples": 24,
}


def merge_adaptive_config(config: dict | None) -> dict:
    merged = dict(DEFAULT_ADAPTIVE_CONFIG)
    merged.update(dict(config or {}))
    return merged


def sample_energy(sample: dict) -> float:
    """Estimate action intensity for adaptive resampling."""
    signals = sample.get("gameplay_signals") or sample.get("signals") or {}
    motion = float(signals.get("motion_intensity", sample.get("motion_score", 0)))
    audio = float(signals.get("audio_spike_score", 0))
    bonus = 0.0
    if signals.get("hitmarker_detected"):
        bonus += 8.0
    if signals.get("killfeed_ocr_match"):
        bonus += 10.0
    if signals.get("low_health_detected"):
        bonus += 4.0
    return motion + (audio * 0.35) + bonus


def build_adaptive_sample_starts(
    *,
    duration: float,
    base_starts: Iterable[float],
    peak_samples: Iterable[dict],
    max_samples: int,
    adaptive_config: dict | None = None,
) -> list[float]:
    """Merge coarse grid starts with dense windows around the strongest samples."""
    cfg = merge_adaptive_config(adaptive_config)
    starts = [round(float(value), 3) for value in base_starts]
    ranked = sorted(peak_samples, key=sample_energy, reverse=True)
    peak_count = max(int(cfg.get("peak_count", 5)), 1)
    dense_interval = max(float(cfg.get("dense_interval_seconds", 0.5)), 0.25)
    peak_window = max(float(cfg.get("peak_window_seconds", 3.0)), 0.5)
    max_start = max(0.0, duration - 0.5)

    dense_starts: list[float] = []
    for sample in ranked[:peak_count]:
        center = float(sample.get("timestamp", 0))
        current = center - peak_window
        end = center + peak_window
        while current <= end + 1e-6:
            dense_starts.append(round(max(0.0, min(current, max_start)), 3))
            current += dense_interval

    combined = sorted(set(starts + dense_starts))
    if len(combined) <= max_samples:
        logger.info(
            "[AdaptiveSampling] Using %s sample point(s) (%s dense around %s peak(s))",
            len(combined),
            len(dense_starts),
            min(peak_count, len(ranked)),
        )
        return combined

    dense_set = set(dense_starts)
    dense_kept = [value for value in combined if value in dense_set]
    coarse_kept = [value for value in combined if value not in dense_set]
    if len(dense_kept) >= max_samples:
        indexes = np.linspace(0, len(dense_kept) - 1, max_samples).round().astype(int)
        trimmed = [dense_kept[index] for index in indexes]
    else:
        remaining = max_samples - len(dense_kept)
        if coarse_kept and remaining > 0:
            indexes = np.linspace(0, len(coarse_kept) - 1, remaining).round().astype(int)
            trimmed = dense_kept + [coarse_kept[index] for index in indexes]
        else:
            trimmed = dense_kept
    trimmed = sorted(dict.fromkeys(trimmed))
    logger.info(
        "[AdaptiveSampling] Trimmed adaptive grid to %s/%s sample point(s)",
        len(trimmed),
        len(combined),
    )
    return trimmed
