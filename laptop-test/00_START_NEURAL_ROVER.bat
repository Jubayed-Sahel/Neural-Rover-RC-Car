@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" web_console.py --open-browser
