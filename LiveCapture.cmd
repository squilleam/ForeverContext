@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing project .venv. Install project dependencies first. 1>&2
  exit /b 2
)
".venv\Scripts\python.exe" "tools\live_capture.py" %*
exit /b %errorlevel%
