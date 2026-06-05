"""Pipeline and FFmpeg logging helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_pipeline_logging(log_dir: Path, video_stem: str) -> Path:
    """Configure console and file logging for a pipeline run."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{video_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter("%(message)s")

    for handler in root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            handler.close()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    return log_path
