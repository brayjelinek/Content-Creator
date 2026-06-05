#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found."
  echo "Please install Python 3, then run this launcher again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg and FFprobe are required but were not found."
  echo "Please install FFmpeg, then run this launcher again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "First launch setup: creating a local Python environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import tkinter" >/dev/null 2>&1; then
  echo "Python Tkinter support is required but was not found."
  echo "Install a standard Python build with Tkinter support, then run this launcher again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if ! python -c "import dotenv, cv2" >/dev/null 2>&1; then
  echo "Installing app dependencies. This can take a minute on first launch..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo "Starting Gameplay Auto Editor..."
python desktop_app.py
