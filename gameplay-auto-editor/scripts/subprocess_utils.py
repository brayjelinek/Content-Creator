"""Quiet subprocess helpers to prevent console popups on Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = 0
DETACHED_PROCESS = 0
if sys.platform.startswith("win"):
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def _binary_name(command: list[str]) -> str:
    if not command:
        return ""
    return Path(str(command[0])).name.lower()


def inject_quiet_flags(command: list[str]) -> list[str]:
    """Add FFmpeg/ffprobe quiet flags without duplicating existing ones."""
    if not command:
        return command

    binary = _binary_name(command)
    if binary not in {"ffmpeg", "ffprobe"}:
        return list(command)

    quiet: list[str] = []
    if "-hide_banner" not in command:
        quiet.append("-hide_banner")
    if binary == "ffmpeg":
        if "-loglevel" not in command:
            quiet.extend(["-loglevel", "error"])
        if "-nostats" not in command and "-f" in command and "null" in command:
            quiet.append("-nostats")
    elif "-v" not in command:
        quiet.extend(["-v", "error"])

    if not quiet:
        return list(command)

    updated = list(command)
    insert_at = 1
    if len(updated) > 1 and updated[1] in {"-y", "-n"}:
        insert_at = 2
    for offset, flag in enumerate(quiet):
        updated.insert(insert_at + offset, flag)
    return updated


def _windows_creationflags(*, detached: bool = False) -> int:
    if not sys.platform.startswith("win"):
        return 0
    flags = CREATE_NO_WINDOW
    if detached:
        flags |= DETACHED_PROCESS
    return flags


def run_quiet(
    command: list[str],
    *,
    check: bool = False,
    stage: str = "",
    filter_chain: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with stdout/stderr captured and no console window."""
    quiet_command = inject_quiet_flags(list(command))
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": check,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = _windows_creationflags()

    result = subprocess.run(quiet_command, **kwargs)
    if check and result.returncode != 0:
        details = [f"Subprocess failed{f': {stage}' if stage else ''}", "Command:", " ".join(quiet_command)]
        if filter_chain:
            details.extend(["Filter chain:", filter_chain])
        details.extend(["STDOUT:", result.stdout or "", "STDERR:", result.stderr or ""])
        raise RuntimeError("\n".join(details))
    return result


def popen_quiet(
    command: list[str],
    *,
    detached: bool = False,
) -> subprocess.Popen[str]:
    """Start a subprocess without showing a console window."""
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = _windows_creationflags(detached=detached)
    return subprocess.Popen(command, **kwargs)
