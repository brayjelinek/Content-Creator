# How To Update Without Re-Downloading

You do **not** need to download a new GitHub artifact every time we fix the app.

## Best option for ongoing use

1. Clone the repo once to your computer:
   - https://github.com/brayjelinek/Content-Creator
2. Open the folder:
   - `gameplay-auto-editor`
3. Double-click:
   - `Launch Gameplay Auto Editor.bat`
4. When we push fixes, double-click:
   - `Update Gameplay Auto Editor.bat`

That updater runs `git pull` and gives you the latest code immediately.

## One-time setup

Install once on Windows:

1. Git for Windows
2. Python 3
3. FFmpeg

The launcher installs Python packages automatically on first run.

## When to use GitHub artifacts

Use the GitHub Actions Windows artifact only if:

- you want a fully packaged app with no Python/Git setup, or
- you are testing a release build

For day-to-day improvements, the source-folder + updater workflow is faster.

## GitHub Actions (free account friendly)

To save Actions minutes and artifact storage:

- **Tests** run on pull requests to `main` only (not every branch push).
- **Windows packaged builds** are **manual only**: GitHub → Actions → **Build desktop app** → **Run workflow**.

Run tests locally before opening a PR:

```bat
cd gameplay-auto-editor
python scripts\test_quality_trust.py
python scripts\test_phase4_features.py
python scripts\test_rollout_phases.py
python scripts\test_caption_quality.py
```

Only trigger a Windows build when you need a fresh `.exe` zip to share or test packaging.
