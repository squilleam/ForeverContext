@echo off
setlocal
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\read_snapshot.py" %*
set "FCTX_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %FCTX_RESULT%
