@echo off
setlocal
cd /d "%~dp0"
title Neural Rover - Test ESP32-CAM

if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL_GPU.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python test_camera.py
pause
