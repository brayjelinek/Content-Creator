# Non-Technical Setup Guide

This project now has two ways to run:

1. A native desktop app window.
2. An optional browser dashboard.

The native desktop app is the recommended non-technical option. The easiest version is the Windows packaged app artifact from GitHub Actions, because it works like a normal downloaded app folder.

## Why you do not see the desktop icon

The icon created by the cloud agent was created on the remote Cursor Cloud computer, not on your personal laptop or desktop. A cloud agent cannot directly place an icon on your local machine.

To see an icon on your own desktop, you need to download this project to your own computer and either run the local launcher installer once or use a packaged app build.

## Best option: packaged app artifact

Use this when you want the closest thing to a normal app:

1. Open the GitHub Actions build named **Build desktop app**.
2. Download `Gameplay-Auto-Editor-Windows`.
3. Unzip it.
4. Open `START_HERE.txt`.
5. Double-click `OPEN_GAMEPLAY_AUTO_EDITOR.bat`.
6. Optionally drag the launcher to your Desktop.

That is the path intended for non-technical testing.

## Source-folder option

Use this only if you downloaded the source project instead of a built app artifact.

### What you need installed once

You need these installed on your computer:

1. Python 3
2. FFmpeg

After those are installed, the launcher will install the remaining Python packages automatically the first time it opens.

If you use a packaged app build from GitHub Actions, Python packages are already bundled. FFmpeg is also bundled when the build process can find it.

### Option 1: Double-click from the project folder

After downloading the project:

### Windows

Double-click:

```text
Launch Gameplay Auto Editor.bat
```

### Mac/Linux source launchers

Mac/Linux source launchers are still present for development, but the packaged build currently targets Windows only.

### Option 2: Create a desktop icon

After downloading the project, open the project folder and run:

```bash
python3 install_desktop_launcher.py
```

On Windows, if `python3` does not work, run:

```bash
python install_desktop_launcher.py
```

This creates a launcher on your Desktop named:

```text
Gameplay Auto Editor
```

## How you use the app after launch

1. Double-click the launcher.
2. A desktop app window opens.
3. Choose a gameplay video.
4. Paste/save your OpenAI API key if needed.
5. For the first test, set **Max AI frames** to 5-10.
6. Click **Generate sample clips**.
7. Review the generated clips.
8. Play, export, or copy captions for the clips you want to post.

## How long OpenAI analysis takes

OpenAI mode analyzes sampled frames one at a time. A short test with 5-10 frames may take a few minutes. A larger run with 20+ frames can take much longer depending on API speed and rate limits.

If the app seems slow:

1. Close and reopen it.
2. Set **Vision mode** to `heuristic` for a fast local test, or keep `openai` and lower **Max AI frames** to 5.
3. Run the same video again.

## Packaging details

The project includes packaging support for a normal desktop build:

```text
build_desktop_app.py
PACKAGING.md
.github/workflows/build-desktop-app.yml
```

The easiest app-style workflow is:

1. Run the GitHub Actions desktop build.
2. Download the artifact for your operating system.
3. Open **Gameplay Auto Editor** like a normal app.

This avoids editing code or running terminal commands after the app artifact is built.
