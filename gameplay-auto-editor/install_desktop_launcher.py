"""Create a desktop launcher for the Gameplay Auto Editor dashboard."""

from __future__ import annotations

from pathlib import Path


APP_NAME = "Gameplay Auto Editor"


def main() -> int:
    app_dir = Path(__file__).resolve().parent
    launch_script = app_dir / "launch_dashboard.sh"
    desktop_dir = Path.home() / "Desktop"
    desktop_file = desktop_dir / f"{APP_NAME}.desktop"

    if not launch_script.exists():
        raise FileNotFoundError(f"Missing launcher script: {launch_script}")

    desktop_dir.mkdir(parents=True, exist_ok=True)
    launch_script.chmod(launch_script.stat().st_mode | 0o755)

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

    print(f"Created desktop launcher: {desktop_file}")
    print(f"Double-click '{APP_NAME}' on your desktop to open the dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
