"""Load game-specific detection profiles for ROI-aware scoring."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _profiles_dir() -> Path:
    import sys

    bundled = Path(getattr(sys, "_MEIPASS", ""))
    if bundled:
        candidate = bundled / "detection_profiles"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[1] / "detection_profiles"


PROFILES_DIR = _profiles_dir()

DEFAULT_PROFILE: dict[str, Any] = {
    "id": "generic",
    "label": "Generic FPS",
    "killfeed_roi": {"x": 0.55, "y": 0.0, "w": 0.45, "h": 0.28},
    "health_roi": {"x": 0.0, "y": 0.78, "w": 0.28, "h": 0.22},
    "hitmarker_roi": {"x": 0.35, "y": 0.35, "w": 0.30, "h": 0.30},
    "facecam_corners": ["bottom_left", "top_right", "top_left", "bottom_right"],
    "hitmarker_red_threshold": 180,
    "hitmarker_white_threshold": 200,
    "hitmarker_flash_threshold": 35,
    "killfeed_keywords": [
        "eliminated",
        "killed",
        "downed",
        "headshot",
        "double kill",
        "squad wipe",
        "knocked",
        "assist",
    ],
    "score_weights": {
        "hitmarker_bonus": 20,
        "killfeed_bonus": 40,
        "low_health_bonus": 15,
        "audio_spike_bonus": 10,
    },
}


def list_profiles() -> list[dict[str, str]]:
    """Return available profile ids and labels."""
    profiles = [{"id": "generic", "label": "Generic FPS"}]
    if not PROFILES_DIR.exists():
        return profiles

    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        profile_id = str(data.get("id") or path.stem)
        if profile_id == "generic":
            continue
        profiles.append({"id": profile_id, "label": str(data.get("label") or profile_id.title())})
    return profiles


def load_profile(profile_id: str | None) -> dict[str, Any]:
    """Load a detection profile by id, falling back to generic."""
    merged = deepcopy(DEFAULT_PROFILE)
    key = str(profile_id or "generic").strip().lower() or "generic"
    if key == "generic":
        bundled = PROFILES_DIR / "generic.json"
        if bundled.exists():
            merged.update(json.loads(bundled.read_text(encoding="utf-8")))
        return merged

    path = PROFILES_DIR / f"{key}.json"
    if not path.exists():
        logger.warning("[DetectionProfile] Unknown profile '%s' — using generic", key)
        return load_profile("generic")

    try:
        merged.update(json.loads(path.read_text(encoding="utf-8")))
        merged["id"] = key
        logger.info("[DetectionProfile] Loaded profile: %s", merged.get("label", key))
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DetectionProfile] Failed to load '%s': %s — using generic", key, exc)
        return load_profile("generic")


def crop_region(frame_shape: tuple[int, ...], roi: dict[str, float]):
    """Convert normalized ROI dict into pixel slice coordinates."""
    height, width = frame_shape[:2]
    x = max(0.0, min(1.0, float(roi.get("x", 0))))
    y = max(0.0, min(1.0, float(roi.get("y", 0))))
    w = max(0.05, min(1.0, float(roi.get("w", 0.2))))
    h = max(0.05, min(1.0, float(roi.get("h", 0.2))))

    x1 = int(width * x)
    y1 = int(height * y)
    x2 = min(width, int(width * (x + w)))
    y2 = min(height, int(height * (y + h)))
    return y1, y2, x1, x2


def merge_profile_weights(highlight_config: dict, profile: dict[str, Any]) -> dict[str, Any]:
    """Merge profile-specific scoring bonuses into highlight detection config."""
    merged = dict(highlight_config or {})
    weights = dict(merged.get("weighted_scoring") or {})
    profile_weights = dict(profile.get("score_weights") or {})
    for key in ("hitmarker_bonus", "killfeed_bonus", "low_health_bonus", "audio_spike_bonus", "chat_spike_bonus"):
        if key in profile_weights:
            weights[key] = profile_weights[key]
    merged["weighted_scoring"] = weights
    merged["game_profile"] = profile.get("id", "generic")
    return merged
