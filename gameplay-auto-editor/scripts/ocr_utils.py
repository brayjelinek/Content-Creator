"""Safe Tesseract OCR helpers for killfeed detection."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

TESSERACT_INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"

DEFAULT_WINDOWS_TESSERACT = Path(r"C:/Program Files/Tesseract-OCR/tesseract.exe")

KILLFEED_KEYWORDS = (
    "eliminated",
    "killed",
    "downed",
    "headshot",
    "double kill",
    "squad wipe",
    "knocked",
    "assist",
)

_OCR_READY = False
_OCR_UNAVAILABLE_LOGGED = False
_RESOLVED_TESSERACT_PATH: str | None = None


def initialize_ocr(ocr_config: dict | None = None) -> dict[str, Any]:
    """Detect Tesseract once per run and configure pytesseract if available."""
    global _OCR_READY, _OCR_UNAVAILABLE_LOGGED, _RESOLVED_TESSERACT_PATH

    _OCR_READY = False
    cfg = dict(ocr_config or {})
    if not cfg.get("enabled", True):
        logger.info("[OCR] OCR unavailable — skipping (disabled in config)")
        _OCR_READY = False
        return _status_payload(available=False, reason="disabled")

    tesseract_path = resolve_tesseract_path(cfg.get("tesseract_path"))
    _RESOLVED_TESSERACT_PATH = tesseract_path

    if not tesseract_path:
        if not _OCR_UNAVAILABLE_LOGGED:
            logger.info("[OCR] OCR unavailable — skipping")
            logger.info(
                "[OCR] Install Tesseract for killfeed detection: %s",
                cfg.get("install_url", TESSERACT_INSTALL_URL),
            )
            if sys.platform.startswith("win"):
                logger.info(
                    "[OCR] After install, set config ocr.tesseract_path to: %s",
                    DEFAULT_WINDOWS_TESSERACT.as_posix(),
                )
            _OCR_UNAVAILABLE_LOGGED = True
        _OCR_READY = False
        return _status_payload(available=False, reason="not_installed")

    try:
        import pytesseract  # type: ignore[import-not-found]

        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        _ = pytesseract.get_tesseract_version()
        _OCR_READY = True
        logger.info("[OCR] Tesseract ready: %s", tesseract_path)
        return _status_payload(available=True, tesseract_path=tesseract_path)
    except Exception as exc:  # noqa: BLE001
        if not _OCR_UNAVAILABLE_LOGGED:
            logger.info("[OCR] OCR unavailable — skipping")
            logger.info("[OCR] pytesseract/Tesseract error: %s", exc)
            logger.info("[OCR] Install guide: %s", cfg.get("install_url", TESSERACT_INSTALL_URL))
            _OCR_UNAVAILABLE_LOGGED = True
        _OCR_READY = False
        return _status_payload(available=False, reason=str(exc))


def resolve_tesseract_path(configured_path: str | None = None) -> str | None:
    """Locate tesseract.exe from config, PATH, or common install locations."""
    candidates: list[Path] = []

    env_path = shutil.which("tesseract")
    if env_path:
        candidates.append(Path(env_path))

    if configured_path:
        candidates.append(Path(configured_path))

    if sys.platform.startswith("win"):
        candidates.extend(
            [
                DEFAULT_WINDOWS_TESSERACT,
                Path(r"C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
            ]
        )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/usr/local/bin/tesseract"),
                Path("/opt/homebrew/bin/tesseract"),
            ]
        )
    else:
        candidates.extend(
            [
                Path("/usr/bin/tesseract"),
                Path("/usr/local/bin/tesseract"),
            ]
        )

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return candidate.as_posix()
    return None


def read_killfeed_region(frame: str | Path | np.ndarray) -> dict | None:
    """OCR the top-right killfeed region. Returns None if OCR is unavailable or fails."""
    if not _OCR_READY:
        return None

    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image
    except ImportError:
        logger.info("[OCR] OCR unavailable — skipping")
        return None

    image = _load_frame(frame)
    if image is None:
        return None

    crop = _killfeed_crop(image)
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.convertScaleAbs(gray, alpha=1.4, beta=10)
    pil_image = Image.fromarray(gray)

    if _RESOLVED_TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = _RESOLVED_TESSERACT_PATH

    try:
        text = pytesseract.image_to_string(pil_image, config="--psm 6").strip()
    except Exception as exc:  # noqa: BLE001
        logger.info("[OCR] OCR unavailable — skipping")
        logger.debug("[OCR] OCR read failed: %s", exc)
        return None

    normalized = " ".join(text.lower().split())
    if not normalized:
        logger.info("[OCR] No killfeed detected")
        return {"text": "", "matched": False, "keyword": None}

    keyword = _match_killfeed_keyword(normalized)
    if keyword:
        logger.info("[OCR] Killfeed detected: %s", normalized[:160])
        return {"text": normalized[:160], "matched": True, "keyword": keyword}

    logger.info("[OCR] No killfeed detected")
    return {"text": normalized[:160], "matched": False, "keyword": None}


def is_ocr_available() -> bool:
    """Return True when OCR has been initialized successfully."""
    return _OCR_READY


def _match_killfeed_keyword(text: str) -> str | None:
    for keyword in sorted(KILLFEED_KEYWORDS, key=len, reverse=True):
        if keyword in text:
            return keyword
    return None


def _killfeed_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    return frame[0 : int(height * 0.28), int(width * 0.55) : width]


def _load_frame(frame: str | Path | np.ndarray) -> np.ndarray | None:
    if isinstance(frame, np.ndarray):
        return frame
    image = cv2.imread(str(frame))
    return image


def _status_payload(*, available: bool, reason: str = "", tesseract_path: str | None = None) -> dict[str, Any]:
    return {
        "available": available,
        "reason": reason,
        "tesseract_path": tesseract_path,
        "install_url": TESSERACT_INSTALL_URL,
    }
