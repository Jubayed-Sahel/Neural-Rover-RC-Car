@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL.bat first.
  pause
  exit /b 1
)
echo Stop the camera in the dashboard before using this enrollment shortcut.
echo Three clear, distinct views will be collected. No images are saved.
".venv\Scripts\python.exe" -u enroll_live.py
pause
