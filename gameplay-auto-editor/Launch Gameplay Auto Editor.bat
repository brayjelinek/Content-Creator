@echo off
setlocal

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required but was not found.
  echo Please install Python from https://www.python.org/downloads/ and check "Add python.exe to PATH".
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg is required but was not found.
  echo Please install FFmpeg, then run this launcher again.
  pause
  exit /b 1
)

where ffprobe >nul 2>nul
if errorlevel 1 (
  echo FFprobe is required but was not found.
  echo Please install FFmpeg, then run this launcher again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First launch setup: creating a local Python environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create the Python environment.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import streamlit, dotenv, cv2" >nul 2>nul
if errorlevel 1 (
  echo Installing dashboard dependencies. This can take a minute on first launch...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo Starting Gameplay Auto Editor...
echo If a browser does not open automatically, copy the Local URL shown below.
".venv\Scripts\python.exe" -m streamlit run dashboard.py
pause
