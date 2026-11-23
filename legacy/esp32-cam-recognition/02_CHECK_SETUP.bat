@echo off
setlocal
cd /d "%~dp0"
title Neural Rover - Check GPU setup

if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL_GPU.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python check_setup.py
pause
