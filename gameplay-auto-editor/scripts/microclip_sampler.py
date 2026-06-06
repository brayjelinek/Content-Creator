"""Extract short microclips for AI scoring instead of single-frame sampling."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np

from scripts.gameplay_signals import analyze_microclip_signals, audio_waveform_summary

logger = logging.getLogger(__name__)


@dataclass
class MicroclipSample:
    timestamp: float
    duration: float
    clip_path: str
    poster_frame_path: str
    killfeed_crop_path: str
    health_crop_path: str
    motion_score: float
    brightness: float
    sharpness: float
    audio_summary: str
    gameplay_signals: dict


def extract_microclips(
    video_path: str | Path,
    output_dir: str | Path,
    interval_seconds: float = 1.0,
    clip_duration: float = 1.5,
    max_samples: int = 60,
    jpeg_quality: int = 85,
    detection_profile: dict | None = None,
) -> List[dict]:
    """Sample 1–2 second microclips every N seconds for downstream analysis."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    clip_dir = output_dir / "clips"
    frame_dir = output_dir / "frames"
    crop_dir = output_dir / "crops"
    for path in (clip_dir, frame_dir, crop_dir):
        path.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    duration = _probe_duration(video_path)
    interval_seconds = max(float(interval_seconds), 0.5)
    clip_duration = max(min(float(clip_duration), 2.0), 1.0)
    max_samples = max(int(max_samples), 1)

    sample_starts = _build_sample_starts(duration, interval_seconds, max_samples)
    expected_count = len(sample_starts)
    logger.info(
        "[MicroclipSampler] Video %.2fs — extracting %s microclip(s) of %.1fs every %.1fs",
        duration,
        expected_count,
        clip_duration,
        interval_seconds,
    )

    samples: list[MicroclipSample] = []
    skipped = 0

    for index, start in enumerate(sample_starts):
        max_start = max(0.0, duration - 0.5)
        safe_start = max(0.0, min(float(start), max_start))
        if safe_start >= duration:
            skipped += 1
            continue

        safe_duration = min(clip_duration, max(duration - safe_start, 0.5))
        clip_path = clip_dir / f"micro_{index:04d}_{safe_start:.2f}s.mp4"

        if not _cut_microclip(video_path, clip_path, safe_start, safe_duration):
            skipped += 1
            logger.warning("[MicroclipSampler] Skipped microclip at %.2fs", safe_start)
            continue

        poster_path = frame_dir / f"micro_{index:04d}_{safe_start:.2f}s.jpg"
        killfeed_path = crop_dir / f"micro_{index:04d}_{safe_start:.2f}s_killfeed.jpg"
        health_path = crop_dir / f"micro_{index:04d}_{safe_start:.2f}s_health.jpg"
        metrics = _extract_poster_and_crops(
            clip_path,
            poster_path,
            killfeed_path,
            health_path,
            jpeg_quality,
            detection_profile,
        )
        if metrics is None:
            skipped += 1
            continue

        signals = analyze_microclip_signals(clip_path, poster_path, detection_profile)
        audio_summary = audio_waveform_summary(clip_path)

        samples.append(
            MicroclipSample(
                timestamp=round(safe_start + (safe_duration / 2.0), 2),
                duration=round(safe_duration, 2),
                clip_path=str(clip_path),
                poster_frame_path=str(poster_path),
                killfeed_crop_path=str(killfeed_path),
                health_crop_path=str(health_path),
                motion_score=round(float(signals.get("motion_intensity", metrics["motion_score"])), 2),
                brightness=metrics["brightness"],
                sharpness=metrics["sharpness"],
                audio_summary=audio_summary,
                gameplay_signals=signals,
            )
        )

    if skipped:
        logger.warning("[MicroclipSampler] Skipped %s microclip sample(s)", skipped)
    logger.info(
        "[MicroclipSampler] Extracted %s usable microclip sample(s) (expected %s)",
        len(samples),
        expected_count,
    )
    return [asdict(sample) for sample in samples]


def _build_sample_starts(duration: float, interval_seconds: float, max_samples: int) -> List[float]:
    if duration <= 0:
        return [0.0]

    interval_seconds = max(float(interval_seconds), 0.5)
    min_tail = 0.5
    max_start = max(0.0, duration - min_tail)

    starts: list[float] = []
    current = 0.0
    while current <= max_start + 1e-6:
        starts.append(round(current, 3))
        current += interval_seconds

    starts = [float(max(0.0, min(value, max_start))) for value in starts]
    starts = list(dict.fromkeys(starts))

    if len(starts) > max_samples:
        indexes = np.linspace(0, len(starts) - 1, max_samples).round().astype(int)
        starts = [starts[index] for index in indexes]

    return starts


def _cut_microclip(video_path: Path, output_path: Path, start: float, duration: float) -> bool:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.2f}",
        "-i",
        str(video_path),
        "-t",
        f"{duration:.2f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _extract_poster_and_crops(
    clip_path: Path,
    poster_path: Path,
    killfeed_path: Path,
    health_path: Path,
    jpeg_quality: int,
    detection_profile: dict | None = None,
) -> dict | None:
    from scripts.detection_profiles import crop_region

    profile = dict(detection_profile or {})
    killfeed_roi = profile.get("killfeed_roi") or {"x": 0.55, "y": 0.0, "w": 0.45, "h": 0.28}
    health_roi = profile.get("health_roi") or {"x": 0.0, "y": 0.78, "w": 0.28, "h": 0.22}

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(total // 2, 0))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    ky1, ky2, kx1, kx2 = crop_region(frame.shape, killfeed_roi)
    hy1, hy2, hx1, hx2 = crop_region(frame.shape, health_roi)
    killfeed = frame[ky1:ky2, kx1:kx2]
    health = frame[hy1:hy2, hx1:hx2]

    cv2.imwrite(str(poster_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
    cv2.imwrite(str(killfeed_path), killfeed, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
    cv2.imwrite(str(health_path), health, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])

    return {
        "motion_score": 0.0,
        "brightness": round(float(np.mean(gray)), 2),
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
    }


def _probe_duration(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        return max(0.0, float((result.stdout or "0").strip()))
    except ValueError:
        return 0.0
