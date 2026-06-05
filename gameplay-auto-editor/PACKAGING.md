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

This repository includes:

```text
.github/workflows/build-desktop-app.yml
```

The workflow builds artifacts for:

- Windows
- macOS
- Linux

After the workflow runs, download the artifact for your operating system from the GitHub Actions run.

## FFmpeg

The build script tries to bundle `ffmpeg` and `ffprobe` if they are available on the build machine. The GitHub Actions workflow installs FFmpeg before building, so those binaries should be included in the generated app artifact.

## API keys

Do not bundle private API keys into release builds.

The desktop app has a field where the user can paste and save an OpenAI API key. The key is saved locally on that user's computer.
