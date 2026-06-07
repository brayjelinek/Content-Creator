# Desktop App Packaging

The native app entry point is:

```text
desktop_app.py
```

It opens a normal desktop window. Users can select a gameplay video, generate clips, review results, open clips, export copies, and save an OpenAI API key without editing files.

## Build locally

Builds must be created on the same operating system you want to distribute:

- Build Windows `.exe` on Windows
- Build Mac `.app` on macOS
- Build Linux executable on Linux

Install dependencies:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
```

Build:

```bash
python build_desktop_app.py
```

The app appears in:

```text
dist/Gameplay Auto Editor/
```

Copy that folder to the target computer and open the app inside it.

## GitHub Actions builds

The workflow lives at:

```text
.github/workflows/build-desktop-app.yml
```

It builds a **Windows** packaged app. To avoid using Actions minutes on every code push, the workflow is **manual only**:

1. Open the repo on GitHub
2. Go to **Actions** → **Build desktop app**
3. Click **Run workflow** → choose branch `main` → **Run workflow**
4. When it finishes, download the artifact (kept for 7 days)

Use this when you need a shareable zip without installing Python locally. For daily development, prefer `Launch Gameplay Auto Editor.bat` after `git pull` instead.

## FFmpeg

The build script tries to bundle `ffmpeg` and `ffprobe` if they are available on the build machine. The GitHub Actions workflow installs FFmpeg before building, so those binaries should be included in the generated app artifact.

## API keys

Do not bundle private API keys into release builds.

The desktop app has a field where the user can paste and save an OpenAI API key. The key is saved locally on that user's computer.
