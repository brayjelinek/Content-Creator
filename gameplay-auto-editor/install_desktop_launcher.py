"""Create a desktop launcher for the Gameplay Auto Editor dashboard."""

from __future__ import annotations

import platform
import shutil
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
    print(f"Double-click '{APP_NAME}' on your desktop to open the dashboard.")
    return 0


def _install_windows_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    source = app_dir / f"{APP_NAME}.bat"
    destination = desktop_dir / source.name
    if not source.exists():
        raise FileNotFoundError(f"Missing launcher script: {source}")

    shutil.copyfile(source, destination)
    return destination


def _install_mac_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    source = app_dir / f"{APP_NAME}.command"
    destination = desktop_dir / source.name
    if not source.exists():
        raise FileNotFoundError(f"Missing launcher script: {source}")

    shutil.copyfile(source, destination)
    destination.chmod(destination.stat().st_mode | 0o755)
    _make_executable(app_dir / "launch_dashboard.sh")
    return destination


def _install_linux_launcher(app_dir: Path, desktop_dir: Path) -> Path:
    launch_script = app_dir / "launch_dashboard.sh"
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


if __name__ == "__main__":
    raise SystemExit(main())
