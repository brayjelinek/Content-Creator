@echo off
setlocal
cd /d "%~dp0"

echo Updating Gameplay Auto Editor from GitHub...
where git >nul 2>&1
if errorlevel 1 (
  echo Git is not installed. Install Git for Windows, then run this updater again.
  pause
  exit /b 1
)

git pull origin cursor/gameplay-auto-editor-8122
if errorlevel 1 (
  git pull origin main
)

echo.
echo Update complete.
echo Double-click "Launch Gameplay Auto Editor.bat" to open the latest version.
pause
