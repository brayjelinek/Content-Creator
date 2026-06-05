# Non-Technical Setup Guide

This project currently runs as a local web dashboard. That means it opens in your browser, but the video processing happens on the computer where the project is installed.

## Why you do not see the desktop icon

The icon created by the cloud agent was created on the remote Cursor Cloud computer, not on your personal laptop or desktop. A cloud agent cannot directly place an icon on your local machine.

To see an icon on your own desktop, you need to download this project to your own computer and run the local launcher installer once.

## What you need installed once

You need these installed on your computer:

1. Python 3
2. FFmpeg

After those are installed, the launcher will install the remaining Python packages automatically the first time it opens.

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
launch_dashboard.sh
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
2. A browser page opens.
3. Upload or drag in your gameplay video.
4. Click **Generate sample clips**.
5. Watch the generated vertical clips.
6. Download the clips you want to post.

## Current limitation

This is not yet a fully packaged consumer app installer like a `.dmg` or `.exe`. The next improvement would be packaging it into a true desktop app installer so you do not need to think about Python, FFmpeg, or project folders.
