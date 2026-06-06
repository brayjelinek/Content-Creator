"""Optional smart vertical reframe with facecam-aware gameplay split layout."""

from __future__ import annotations

import logging
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.render_settings import merge_render_config

logger = logging.getLogger(__name__)

CORNER_REGIONS = {
    "top_left": (0.0, 0.0, 0.28, 0.28),
    "top_right": (0.72, 0.0, 0.28, 0.28),
    "bottom_left": (0.0, 0.72, 0.28, 0.28),
    "bottom_right": (0.72, 0.72, 0.28, 0.28),
}


def merge_reframe_settings(render_config: dict | None, source_path: str | Path | None) -> dict[str, Any]:
    """Analyze source clip and attach reframe metadata to render settings."""
    settings = merge_render_config(render_config)
    reframe_cfg = dict(settings.get("smart_reframe") or {})
    if not reframe_cfg.get("enabled", False) or not source_path:
        return settings

    source_path = Path(source_path)
    if not source_path.exists():
        return settings

    preferred = reframe_cfg.get("facecam_corners") or settings.get("facecam_corners")
    analysis = analyze_facecam_layout(source_path, reframe_cfg, preferred)
    if not analysis:
        logger.info("[SmartReframe] No facecam detected — using center crop")
        return settings

    merged = deepcopy(settings)
    merged["reframe_analysis"] = analysis
    logger.info(
        "[SmartReframe] Using %s layout (facecam=%s score=%.1f)",
        analysis.get("layout"),
        analysis.get("corner"),
        float(analysis.get("score", 0)),
    )
    return merged


def apply_smart_reframe(input_path: Path, output_path: Path, settings: dict) -> bool:
    """Render a facecam/gameplay split vertical clip. Returns False on failure."""
    analysis = settings.get("reframe_analysis")
    if not analysis:
        return False

    width = int(settings["width"])
    height = int(settings["height"])
    face_ratio = float(analysis.get("facecam_ratio", 0.30))
    face_h = max(1, int(height * face_ratio))
    game_h = max(1, height - face_h)
    x1, y1, x2, y2 = analysis.get("facecam_box") or (0, 0, 1, 1)
    face_w = max(1, int(x2) - int(x1))
    face_h_src = max(1, int(y2) - int(y1))

    filter_complex = (
        f"[0:v]split=2[face_src][game_src];"
        f"[face_src]crop={face_w}:{face_h_src}:{x1}:{y1},"
        f"scale={width}:{face_h}:force_original_aspect_ratio=increase,crop={width}:{face_h},setsar=1[face];"
        f"[game_src]scale={width}:{game_h}:force_original_aspect_ratio=increase,crop={width}:{game_h},setsar=1[game];"
        f"[face][game]vstack=inputs=2,format=yuv420p[vout]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        str(settings["preset"]),
        "-crf",
        str(settings["video_crf"]),
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.warning("[SmartReframe] Reframe failed: %s", (result.stderr or "").strip())
            return False
        if not output_path.exists() or output_path.stat().st_size <= 0:
            return False
        logger.info("[SmartReframe] Applied %s layout to %s", analysis.get("layout"), output_path.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SmartReframe] Reframe skipped: %s", exc)
        return False


def analyze_facecam_layout(
    source_path: Path,
    reframe_cfg: dict | None = None,
    preferred_corners: list[str] | None = None,
) -> dict[str, Any] | None:
    """Detect a likely facecam corner and return layout metadata."""
    reframe_cfg = dict(reframe_cfg or {})
    min_score = float(reframe_cfg.get("min_facecam_score", 18.0))
    frame = _read_middle_frame(source_path)
    if frame is None:
        return None

    corners = preferred_corners or reframe_cfg.get("facecam_corners") or list(CORNER_REGIONS)
    best_corner = None
    best_score = 0.0
    best_box = None

    height, width = frame.shape[:2]
    for corner in corners:
        if corner not in CORNER_REGIONS:
            continue
        x, y, w, h = CORNER_REGIONS[corner]
        x1, x2 = int(width * x), int(width * (x + w))
        y1, y2 = int(height * y), int(height * (y + h))
        region = frame[y1:y2, x1:x2]
        if region.size == 0:
            continue
        score = _facecam_score(region)
        if score > best_score:
            best_score = score
            best_corner = corner
            best_box = (x1, y1, x2, y2)

    if best_corner is None or best_score < min_score:
        return None

    return {
        "layout": str(reframe_cfg.get("layout", "gameplay_split")),
        "corner": best_corner,
        "score": round(best_score, 2),
        "facecam_box": best_box,
        "facecam_ratio": max(0.20, min(float(reframe_cfg.get("facecam_ratio", 0.30)), 0.40)),
        "source_width": width,
        "source_height": height,
    }


def _read_middle_frame(source_path: Path) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(total // 2, 0))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _facecam_score(region: np.ndarray) -> float:
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float(np.mean(edges > 0))
    variance = float(np.var(gray))
    return edge_density * 120.0 + min(variance / 20.0, 40.0)
