"""Build the native desktop app with PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "Gameplay Auto Editor"
ROOT = Path(__file__).resolve().parent


def main() -> int:
    _ensure_pyinstaller()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        _data_arg(ROOT / "config.json", "."),
        "--add-data",
        _data_arg(ROOT / ".env.example", "."),
        "--hidden-import",
        "openai",
        "--hidden-import",
        "anthropic",
        "--hidden-import",
        "cv2",
    ]

    for binary_name in ["ffmpeg", "ffprobe"]:
        binary_path = _find_binary(binary_name)
        if binary_path:
            print(f"Bundling {binary_name}: {binary_path}")
            command.extend(["--add-binary", _data_arg(binary_path, "bin")])
        else:
            print(f"Warning: {binary_name} was not found. Built app will require it on PATH.")

    command.append(str(ROOT / "desktop_app.py"))
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)

    dist_dir = ROOT / "dist"
    output = dist_dir / APP_NAME
    _write_start_here(dist_dir)
    _write_top_level_launcher(dist_dir)
    print(f"\nBuild complete: {output}")
    print(f"Download or copy everything in: {dist_dir}")
    print("Open START_HERE.txt for simple click-by-click instructions.")
    return 0


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt"
        ) from exc


def _data_arg(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def _find_binary(binary_name: str) -> Path | None:
    """Find the real FFmpeg binary, avoiding Chocolatey shim executables."""
    executable_name = binary_name + (".exe" if sys.platform.startswith("win") else "")

    if sys.platform.startswith("win"):
        chocolatey_root = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
        candidates = [
            chocolatey_root / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / executable_name,
            chocolatey_root / "lib" / "ffmpeg-full" / "tools" / "ffmpeg" / "bin" / executable_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

    binary_path = shutil.which(binary_name)
    if not binary_path:
        return None

    return Path(binary_path)


def _write_start_here(dist_dir: Path) -> None:
    if sys.platform.startswith("win"):
        instructions = [
            "Gameplay Auto Editor - Windows",
            "",
            "1. Unzip the downloaded artifact first.",
            "2. Open the folder.",
            "3. Double-click OPEN_GAMEPLAY_AUTO_EDITOR.bat.",
            "",
            "If that does not work, open this file instead:",
            "Gameplay Auto Editor\\Gameplay Auto Editor.exe",
            "",
            "You do not need to choose another program to open it.",
        ]
    elif sys.platform == "darwin":
        instructions = [
            "Gameplay Auto Editor - Mac",
            "",
            "1. Unzip the downloaded artifact first.",
            "2. Double-click Gameplay Auto Editor.app.",
            "",
            "If Mac blocks it:",
            "1. Right-click Gameplay Auto Editor.app.",
            "2. Click Open.",
            "3. Click Open again if macOS asks for confirmation.",
            "",
            "You do not need to choose another program to open it.",
        ]
    else:
        instructions = [
            "Gameplay Auto Editor - Linux",
            "",
            "1. Unzip the downloaded artifact first.",
            "2. Open the folder.",
            "3. Double-click OPEN_GAMEPLAY_AUTO_EDITOR.sh.",
            "",
            "If your file manager asks what to do, choose Run or Execute.",
            "If that does not work, open a terminal in this folder and run:",
            "./OPEN_GAMEPLAY_AUTO_EDITOR.sh",
        ]

    (dist_dir / "START_HERE.txt").write_text("\n".join(instructions) + "\n", encoding="utf-8")


def _write_top_level_launcher(dist_dir: Path) -> None:
    if sys.platform.startswith("win"):
        launcher = dist_dir / "OPEN_GAMEPLAY_AUTO_EDITOR.bat"
        launcher.write_text(
            "\n".join(
                [
                    "@echo off",
                    'cd /d "%~dp0"',
                    f'start "" "{APP_NAME}\\{APP_NAME}.exe"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
    elif sys.platform == "darwin":
        # The .app bundle already lives at the top level and is the launcher.
        return
    else:
        launcher = dist_dir / "OPEN_GAMEPLAY_AUTO_EDITOR.sh"
        launcher.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    'APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
                    f'exec "$APP_DIR/{APP_NAME}/{APP_NAME}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | 0o755)


if __name__ == "__main__":
    raise SystemExit(main())
