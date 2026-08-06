@echo off
setlocal
cd /d "%~dp0"
title Neural Rover - Install GPU face recognition

echo ============================================================
echo Neural Rover laptop installation for NVIDIA GeForce MX150
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher was not found.
  echo Install 64-bit Python, enable "Add Python to PATH", then retry.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the private Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"

echo Updating installation tools...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :failed

echo Removing conflicting ONNX Runtime packages...
python -m pip uninstall -y onnxruntime onnxruntime-gpu >nul 2>nul

echo Installing InsightFace, OpenCV and CUDA 12 compatible runtime...
python -m pip install -r requirements-gpu.txt
if errorlevel 1 goto :failed

echo.
echo Installation completed. Running the setup check...
python check_setup.py
echo.
echo Next: double-click 03_TEST_CAMERA.bat
pause
exit /b 0

:failed
echo.
echo INSTALLATION FAILED.
echo Read the error above and the troubleshooting section in README.md.
pause
exit /b 1
