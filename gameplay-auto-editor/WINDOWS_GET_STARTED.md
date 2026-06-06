# Windows Get Started (No Git Required)

You do **not** need to know how to "clone" anything.

The easiest way is to **download the project as a ZIP file**.

## Step 1: Download the project

1. Open this page in your browser:
   https://github.com/brayjelinek/Content-Creator
2. Click the green **Code** button (near the top right of the file list).
3. Click **Download ZIP**.
4. Wait for the download to finish.

## Step 2: Unzip it

1. Open your **Downloads** folder.
2. Find `Content-Creator-main.zip` (or similar name).
3. Right-click it.
4. Click **Extract All...**
5. Click **Extract**.

You should now have a folder like:

```text
Downloads/Content-Creator-main/gameplay-auto-editor/
```

## Step 3: Open the app

1. Open the folder:
   `Content-Creator-main` → `gameplay-auto-editor`
2. Double-click:

```text
Launch Gameplay Auto Editor.bat
```

If Windows asks for permission, click **Run** or **More info** → **Run anyway**.

The app window should open.

## Step 4: Use the app

1. Click **Choose gameplay video**
2. Pick your gameplay file
3. For a first test, set **Vision mode** to `heuristic` (fastest)
4. Click **Generate sample clips**
5. Review the clips in the app

## When we release updates

Instead of downloading a new GitHub Actions app every time:

1. Go back to https://github.com/brayjelinek/Content-Creator
2. Click **Code** → **Download ZIP** again
3. Extract it to a new folder (or replace the old folder)
4. Open `gameplay-auto-editor`
5. Double-click `Launch Gameplay Auto Editor.bat` again

## One-time installs (only if the launcher says something is missing)

Install these once on Windows if the app asks:

1. **Python 3** from https://www.python.org/downloads/
   - During install, check **Add Python to PATH**
2. **FFmpeg** from https://www.gyan.dev/ffmpeg/builds/
   - Or install with winget: `winget install Gyan.FFmpeg`
3. **Tesseract OCR** (optional, for killfeed detection) from https://github.com/UB-Mannheim/tesseract/wiki
   - Default install path: `C:/Program Files/Tesseract-OCR/tesseract.exe`
   - Clips still generate without it — OCR adds better kill/multi-kill detection when installed

## If you prefer the packaged app instead

Use the Windows artifact from GitHub Actions:

1. Open the latest **Build desktop app** run on GitHub
2. Download **Gameplay-Auto-Editor-Windows**
3. Unzip it
4. Double-click **OPEN_GAMEPLAY_AUTO_EDITOR.bat**

This packaged version is optional. The ZIP method above is usually easier for updates.
