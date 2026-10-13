@echo off
setlocal
cd /d "%~dp0"
echo Installing CPU laptop pose test in its own environment.
py -3.12 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>nul
if errorlevel 1 (
  echo Please install 64-bit Python 3.12 from python.org with the Python launcher.
  echo This package intentionally uses Python 3.12, not your default Python version.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" setup_package.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" test_pose.py --check
if errorlevel 1 goto failed
echo Installation complete. Next open 02_TEST_LIVE.bat.
pause
exit /b 0
:failed
echo Installation failed. Keep the error above for troubleshooting.
pause
exit /b 1
