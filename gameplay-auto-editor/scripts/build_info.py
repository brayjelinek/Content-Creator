"""Build metadata embedded in packaged desktop apps."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from scripts.pipeline import PROJECT_ROOT

BUNDLED_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
BUILD_INFO_PATH = BUNDLED_ROOT / "build_info.json"


def load_build_info() -> dict[str, str]:
    if not BUILD_INFO_PATH.exists():
        return {}
    try:
        payload = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value}


def format_build_label(info: dict[str, str] | None = None) -> str:
    payload = info if info is not None else load_build_info()
    commit = payload.get("commit_short") or payload.get("commit")
    built_at = payload.get("built_at")
    if not commit and not built_at:
        return "Development build"

    parts: list[str] = []
    if commit:
        parts.append(f"Build {commit}")
    if built_at:
        try:
            stamp = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
            parts.append(stamp.strftime("%Y-%m-%d %H:%M UTC"))
        except ValueError:
            parts.append(built_at)
    return " · ".join(parts)
