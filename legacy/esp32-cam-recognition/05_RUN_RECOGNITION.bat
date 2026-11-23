@echo off
setlocal
cd /d "%~dp0"
title Neural Rover - buffalo_l face recognition

if not exist ".venv\Scripts\python.exe" (
  echo Run 01_INSTALL_GPU.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python face_recognition_stream.py
pause
