"""Build the native desktop app with PyInstaller."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_BASE_NAME = "Gameplay Auto Editor"
ROOT = Path(__file__).resolve().parent


def main() -> int:
    _ensure_pyinstaller()
    fonts_dir = ROOT / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    _prepare_bundled_font(fonts_dir)
    build_info_path, build_info = _write_build_info()
    app_name = _release_folder_name(build_info)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        app_name,
        "--add-data",
        _data_arg(ROOT / "config.json", "."),
        "--add-data",
        _data_arg(ROOT / "detection_profiles", "detection_profiles"),
        "--add-data",
        _data_arg(ROOT / ".env.example", "."),
        "--add-data",
        _data_arg(build_info_path, "."),
    ]

    if (fonts_dir / "DejaVuSans-Bold.ttf").exists():
        command.extend(["--add-data", _data_arg(fonts_dir, "fonts")])

    command.extend(
        [
        "--hidden-import",
        "openai",
        "--hidden-import",
        "anthropic",
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "pytesseract",
        "--hidden-import",
        "PIL",
        "--hidden-import",
        "PIL.Image",
        ]
    )

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
    app_build_dir = dist_dir / app_name
    release_root = _assemble_release_package(dist_dir, app_build_dir, build_info, app_name)
    print(f"\nBuild complete: {app_build_dir}")
    print(f"Release package: {release_root}")
    print("Open START_HERE.txt inside the release folder for instructions.")
    return 0


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt"
        ) from exc


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


def _prepare_bundled_font(fonts_dir: Path) -> None:
    """Copy a known-good font into the app bundle for drawtext on Windows."""
    if (fonts_dir / "DejaVuSans-Bold.ttf").exists():
        return

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            shutil.copy2(candidate, fonts_dir / "DejaVuSans-Bold.ttf")
            print(f"Bundled overlay font: {candidate}")
            return

    print("Warning: no overlay font found to bundle; drawtext may fail on some systems.")


def _data_arg(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def _write_build_info() -> tuple[Path, dict[str, str]]:
    commit = os.environ.get("GITHUB_SHA")
    branch = os.environ.get("GITHUB_REF_NAME")
    if not commit:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            commit = "unknown"
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=ROOT,
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            branch = "unknown"

    payload = {
        "commit": commit,
        "commit_short": commit[:7],
        "branch": branch,
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    build_info_path = ROOT / "build_info.json"
    build_info_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Build info: {payload['commit_short']} ({branch})")
    return build_info_path, payload


def _release_folder_name(build_info: dict[str, str]) -> str:
    commit = build_info.get("commit_short") or "dev"
    return f"{APP_BASE_NAME} ({commit})"


def _release_package_name(build_info: dict[str, str]) -> str:
    commit = build_info.get("commit_short") or "dev"
    return f"Gameplay-Auto-Editor-{commit}"


def _assemble_release_package(
    dist_dir: Path,
    app_build_dir: Path,
    build_info: dict[str, str],
    app_name: str,
) -> Path:
    """Wrap the build in a single versioned folder for clean Windows extraction."""
    release_name = _release_package_name(build_info)
    release_root = dist_dir / release_name
    if release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True)

    if app_build_dir.exists():
        shutil.move(str(app_build_dir), str(release_root / app_name))

    _write_start_here(release_root, build_info, app_name)
    _write_top_level_launcher(release_root, app_name)

    for entry in dist_dir.iterdir():
        if entry.name == release_name:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    return release_root


def _write_start_here(dist_dir: Path, build_info: dict[str, str], app_name: str) -> None:
    commit = build_info.get("commit_short") or "unknown"
    if sys.platform.startswith("win"):
        instructions = [
            f"Gameplay Auto Editor - Windows ({commit})",
            "",
            "How to install this build:",
            "1. Right-click the downloaded zip -> Extract All...",
            "2. Choose Desktop (or any folder you like).",
            f"3. Windows will create ONE new folder: Gameplay-Auto-Editor-{commit}",
            "4. Open that folder and double-click OPEN_GAMEPLAY_AUTO_EDITOR.bat.",
            "",
            "You should NOT see Replace files prompts when extracting to Desktop.",
            "If you do, cancel and pick a different destination folder.",
            "",
            "Extraction can take 1-2 minutes. This package is about 180 MB.",
            "",
            "Verify you have this build:",
            f"- Top folder name is Gameplay-Auto-Editor-{commit}",
            f"- App folder inside is {app_name}",
            "- App header shows Build " + commit,
            "- Sections: Create clips, Review & export, Tools & integrations",
            "",
            "If the launcher does not work, open:",
            f"{app_name}\\{app_name}.exe",
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


def _write_top_level_launcher(dist_dir: Path, app_name: str) -> None:
    if sys.platform.startswith("win"):
        launcher = dist_dir / "OPEN_GAMEPLAY_AUTO_EDITOR.bat"
        launcher.write_text(
            "\n".join(
                [
                    "@echo off",
                    'cd /d "%~dp0"',
                    f'start "" "{app_name}\\{app_name}.exe"',
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
                    f'exec "$APP_DIR/{app_name}/{app_name}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | 0o755)


if __name__ == "__main__":
    raise SystemExit(main())
