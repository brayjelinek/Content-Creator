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
        binary_path = shutil.which(binary_name)
        if binary_path:
            command.extend(["--add-binary", _data_arg(Path(binary_path), "bin")])
        else:
            print(f"Warning: {binary_name} was not found. Built app will require it on PATH.")

    command.append(str(ROOT / "desktop_app.py"))
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)

    output = ROOT / "dist" / APP_NAME
    print(f"\nBuild complete: {output}")
    print("Copy this folder to the target computer and open the app inside it.")
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


if __name__ == "__main__":
    raise SystemExit(main())
