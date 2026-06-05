"""Create a desktop launcher for the Gameplay Auto Editor dashboard."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path


APP_NAME = "Gameplay Auto Editor"


def main() -> int:
    app_dir = Path(__file__).resolve().parent
    desktop_dir = Path.home() / "Desktop"
    desktop_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    if system == "windows":
        desktop_file = _install_windows_launcher(app_dir, desktop_dir)
    elif system == "darwin":
        desktop_file = _install_mac_launcher(app_dir, desktop_dir)
    else:
        desktop_file = _install_linux_launcher(app_dir, desktop_dir)

    print(f"Created desktop launcher: {desktop_file}")
    print(f"Double-click '{APP_NAME}' on your desktop to open the app.")
    return 0


def _install_windows_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    launcher = app_dir / f"{APP_NAME}.bat"
    shortcut = desktop_dir / f"{APP_NAME}.lnk"
    fallback = desktop_dir / launcher.name
    if not launcher.exists():
        raise FileNotFoundError(f"Missing launcher script: {launcher}")

    try:
        _create_windows_shortcut(shortcut, launcher, app_dir)
        return shortcut
    except Exception as exc:  # noqa: BLE001 - use a simple fallback if PowerShell is unavailable.
        print(f"Could not create Windows shortcut, using batch fallback instead: {exc}")

    fallback.write_text(
        "\n".join(
            [
                "@echo off",
                f'cd /d "{app_dir}"',
                f'call "{launcher}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return fallback


def _create_windows_shortcut(shortcut: Path, target: Path, working_dir: Path) -> None:
    ps_command = (
        "$WScriptShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WScriptShell.CreateShortcut('{_ps_escape(shortcut)}'); "
        f"$Shortcut.TargetPath = '{_ps_escape(target)}'; "
        f"$Shortcut.WorkingDirectory = '{_ps_escape(working_dir)}'; "
        "$Shortcut.Description = 'Gameplay Auto Editor'; "
        "$Shortcut.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
        check=True,
        capture_output=True,
        text=True,
    )


def _install_mac_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    launcher = app_dir / "launch_desktop_app.sh"
    destination = desktop_dir / f"{APP_NAME}.command"
    if not launcher.exists():
        raise FileNotFoundError(f"Missing launcher script: {launcher}")

    destination.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'cd "{app_dir}"',
                f'exec "{launcher}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    destination.chmod(destination.stat().st_mode | 0o755)
    _make_executable(launcher)
    return destination


def _install_linux_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    launch_script = app_dir / "launch_desktop_app.sh"
    desktop_file = desktop_dir / f"{APP_NAME}.desktop"

    if not launch_script.exists():
        raise FileNotFoundError(f"Missing launcher script: {launch_script}")

    _make_executable(launch_script)

    desktop_file.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={APP_NAME}",
                "Comment=Upload gameplay videos and generate vertical highlight clips",
                f'Exec=/bin/bash "{launch_script}"',
                "Icon=video-x-generic",
                "Terminal=true",
                "Categories=AudioVideo;Video;",
                "StartupNotify=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_file.chmod(desktop_file.stat().st_mode | 0o755)
    return desktop_file


def _make_executable(path: Path) -> None:
    if path.exists():
        path.chmod(path.stat().st_mode | 0o755)


def _ps_escape(path: Path) -> str:
    return str(path).replace("'", "''")


if __name__ == "__main__":
    raise SystemExit(main())
