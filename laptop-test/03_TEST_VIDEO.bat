@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL.bat first.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Drag a recorded MP4 or AVI file onto this batch file.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" test_pose.py --video "%~1"
pause
