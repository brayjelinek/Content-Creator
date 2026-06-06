"""Optional lightweight gameplay signals for highlight scoring.

All detectors are best-effort: failures return zero/False and never raise.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from scripts.detection_profiles import crop_region
from scripts.ocr_utils import read_killfeed_region

logger = logging.getLogger(__name__)


def analyze_microclip_signals(
    clip_path: str | Path,
    poster_frame_path: str | Path | None = None,
    profile: dict | None = None,
) -> dict:
    """Return optional gameplay signals for one microclip sample."""
    signals = {
        "motion_intensity": 0.0,
        "audio_spike_score": 0.0,
        "hitmarker_detected": False,
        "killfeed_ocr_match": False,
        "killfeed_ocr_text": "",
        "killfeed_ocr_keyword": None,
        "low_health_detected": False,
    }

    clip_path = Path(clip_path)
    if not clip_path.exists():
        return signals

    try:
        signals["motion_intensity"] = round(_motion_intensity(clip_path), 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[GameplaySignals] motion failed for %s: %s", clip_path.name, exc)

    try:
        signals["audio_spike_score"] = round(_audio_spike_score(clip_path), 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[GameplaySignals] audio failed for %s: %s", clip_path.name, exc)

    frame_path = Path(poster_frame_path) if poster_frame_path else _middle_frame_path(clip_path)
    if frame_path and frame_path.exists():
        try:
            signals["hitmarker_detected"] = _detect_hitmarker_flash(clip_path, profile)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[GameplaySignals] hitmarker failed for %s: %s", clip_path.name, exc)

        try:
            ocr_result = read_killfeed_region(frame_path, profile=profile)
            if ocr_result:
                signals["killfeed_ocr_text"] = ocr_result.get("text", "")
                signals["killfeed_ocr_match"] = bool(ocr_result.get("matched", False))
                signals["killfeed_ocr_keyword"] = ocr_result.get("keyword")
        except Exception as exc:  # noqa: BLE001
            logger.debug("[GameplaySignals] killfeed OCR failed for %s: %s", clip_path.name, exc)

        try:
            signals["low_health_detected"] = _detect_low_health(frame_path, profile)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[GameplaySignals] low-health failed for %s: %s", clip_path.name, exc)

    return signals


def audio_waveform_summary(clip_path: str | Path) -> str:
    """Build a short text summary of audio energy for vision prompts."""
    clip_path = Path(clip_path)
    try:
        spike = _audio_spike_score(clip_path)
        mean_db, max_db = _ffmpeg_volume_stats(clip_path)
        if mean_db is None:
            return "No measurable audio energy detected."
        spike_label = "spike detected" if spike >= 10 else "steady audio"
        return f"Audio mean {mean_db:.1f} dB, peak {max_db:.1f} dB, {spike_label}."
    except Exception as exc:  # noqa: BLE001
        logger.debug("[GameplaySignals] waveform summary failed: %s", exc)
        return "Audio summary unavailable."


def _motion_intensity(clip_path: Path) -> float:
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return 0.0

    previous: np.ndarray | None = None
    diffs: list[float] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
        if previous is not None:
            diffs.append(float(np.mean(cv2.absdiff(small, previous))))
        previous = small
    cap.release()
    if not diffs:
        return 0.0
    return min(100.0, float(np.mean(diffs)) * 2.5)


def _audio_spike_score(clip_path: Path) -> float:
    mean_db, max_db = _ffmpeg_volume_stats(clip_path)
    if mean_db is None or max_db is None:
        return 0.0
    delta = max(0.0, max_db - mean_db)
    return min(20.0, delta * 0.8)


def _ffmpeg_volume_stats(clip_path: Path) -> tuple[float | None, float | None]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(clip_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stderr = result.stderr or ""
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
    max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
    mean_db = float(mean_match.group(1)) if mean_match else None
    max_db = float(max_match.group(1)) if max_match else None
    return mean_db, max_db


def _detect_hitmarker_flash(clip_path: Path, profile: dict | None = None) -> bool:
    profile = dict(profile or {})
    roi = profile.get("hitmarker_roi") or {"x": 0.35, "y": 0.35, "w": 0.30, "h": 0.30}
    red_threshold = int(profile.get("hitmarker_red_threshold", 180))
    white_threshold = int(profile.get("hitmarker_white_threshold", 200))
    flash_threshold = float(profile.get("hitmarker_flash_threshold", 35))

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return False

    previous_center: np.ndarray | None = None
    flash_detected = False
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        height, width = frame.shape[:2]
        y1, y2, x1, x2 = crop_region(frame.shape, roi)
        center = frame[y1:y2, x1:x2]
        if center.size == 0:
            continue
        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        red = center[:, :, 2]
        white = gray > white_threshold
        red_hit = red > red_threshold
        if previous_center is not None:
            diff = cv2.absdiff(gray, previous_center)
            bright = (gray > 210) | red_hit | white
            spike = float(np.mean(diff[bright])) if np.any(bright) else 0.0
            if spike >= flash_threshold:
                flash_detected = True
                break
        previous_center = gray
    cap.release()
    return flash_detected


def _detect_low_health(frame_path: Path, profile: dict | None = None) -> bool:
    profile = dict(profile or {})
    roi = profile.get("health_roi") or {"x": 0.0, "y": 0.78, "w": 0.28, "h": 0.22}
    frame = cv2.imread(str(frame_path))
    if frame is None:
        return False

    y1, y2, x1, x2 = crop_region(frame.shape, roi)
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return False

    red = region[:, :, 2].astype(np.float32)
    green = region[:, :, 1].astype(np.float32)
    blue = region[:, :, 0].astype(np.float32)
    red_ratio = float(np.mean(red > (green + 20))) + float(np.mean(red > (blue + 20)))
    return red_ratio >= 0.18


def _middle_frame_path(clip_path: Path) -> Path | None:
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None

    temp = Path(tempfile.gettempdir()) / f"gae_poster_{clip_path.stem}.jpg"
    cv2.imwrite(str(temp), frame)
    return temp
