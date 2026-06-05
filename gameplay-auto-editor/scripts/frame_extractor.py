"""Extract sampled frames and simple visual signals from gameplay footage."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FrameSample:
    timestamp: float
    frame_path: str
    frame_index: int
    motion_score: float
    brightness: float
    sharpness: float


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    interval_seconds: float = 3,
    max_frames: int = 24,
    jpeg_quality: int = 85,
) -> List[dict]:
    """Sample frames from a video and return metadata for downstream analysis."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else 0
    logger.info("[FrameExtractor] Video %.2fs @ %.2ffps (%s frames)", duration, fps, frame_count)

    sample_times = _build_sample_times(duration, interval_seconds, max_frames)
    logger.info("[FrameExtractor] Sampling %s timestamp(s)", len(sample_times))
    samples: List[FrameSample] = []
    previous_gray: np.ndarray | None = None
    skipped = 0

    for index, timestamp in enumerate(sample_times):
        frame_index = int(round(timestamp * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_index, 0))
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
        if not ok:
            skipped += 1
            logger.warning("[FrameExtractor] Could not read frame at %.2fs (index %s)", timestamp, frame_index)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small_gray = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)

        if previous_gray is None:
            motion_score = float(np.mean(small_gray)) * 0.01
        else:
            diff = cv2.absdiff(small_gray, previous_gray)
            motion_score = float(np.mean(diff))
        previous_gray = small_gray

        brightness = float(np.mean(gray))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        frame_file = output_dir / f"frame_{index:04d}_{timestamp:.2f}s.jpg"

        cv2.imwrite(
            str(frame_file),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )

        samples.append(
            FrameSample(
                timestamp=round(float(timestamp), 2),
                frame_path=str(frame_file),
                frame_index=frame_index,
                motion_score=round(motion_score, 2),
                brightness=round(brightness, 2),
                sharpness=round(sharpness, 2),
            )
        )

    cap.release()

    if skipped:
        logger.warning("[FrameExtractor] Skipped %s unreadable frame sample(s)", skipped)
    logger.info("[FrameExtractor] Extracted %s usable frame sample(s)", len(samples))
    return [asdict(sample) for sample in samples]


def _build_sample_times(duration: float, interval_seconds: float, max_frames: int) -> List[float]:
    if duration <= 0:
        return [0.0]

    interval_seconds = max(float(interval_seconds), 0.5)
    max_frames = max(int(max_frames), 1)
    timestamps = list(np.arange(0, max(duration, interval_seconds), interval_seconds))

    if len(timestamps) > max_frames:
        indexes = np.linspace(0, len(timestamps) - 1, max_frames).round().astype(int)
        timestamps = [timestamps[index] for index in indexes]

    return [min(float(timestamp), max(duration - 0.1, 0)) for timestamp in timestamps]
