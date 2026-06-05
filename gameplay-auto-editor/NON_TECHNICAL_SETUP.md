# Non-Technical Setup Guide

This project now has two ways to run:

1. A native desktop app window.
2. An optional browser dashboard.

The native desktop app is the recommended non-technical option.

## Why you do not see the desktop icon

The icon created by the cloud agent was created on the remote Cursor Cloud computer, not on your personal laptop or desktop. A cloud agent cannot directly place an icon on your local machine.

To see an icon on your own desktop, you need to download this project to your own computer and either run the local launcher installer once or use a packaged app build.

## What you need installed once

You need these installed on your computer:

1. Python 3
2. FFmpeg

After those are installed, the launcher will install the remaining Python packages automatically the first time it opens.

If you use a packaged app build from GitHub Actions, Python packages are already bundled. FFmpeg is also bundled when the build process can find it.

## Option 1: Double-click from the project folder

After downloading the project:

### Windows

Double-click:

```text
Launch Gameplay Auto Editor.bat
```

### Mac

Double-click:

```text
Launch Gameplay Auto Editor.command
```

If Mac blocks it, right-click the file, choose **Open**, then approve it.

### Linux

Double-click:

```text
launch_desktop_app.sh
```

## Option 2: Create a desktop icon

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
5. Click **Generate sample clips**.
6. Review the generated clips.
7. Play, export, or copy captions for the clips you want to post.

## Packaged app option

The project includes packaging support for a normal desktop build:

```text
build_desktop_app.py
PACKAGING.md
.github/workflows/build-desktop-app.yml
```

The easiest future workflow is:

1. Run the GitHub Actions desktop build.
2. Download the artifact for your operating system.
3. Open **Gameplay Auto Editor** like a normal app.

This avoids editing code or running terminal commands after the app artifact is built.
