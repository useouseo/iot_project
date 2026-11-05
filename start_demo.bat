@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
) else (
  set "PY_CMD=py -3"
)
if not exist ".venv\Scripts\python.exe" (
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Open http://localhost:8000 in your browser after the server starts.
echo Admin page: http://localhost:8000/admin
echo Admin token is stored locally in .runtime\admin-token after first start.
echo Keep this window open. Press Ctrl+C to stop the server.
echo.
.venv\Scripts\python.exe server.py --demo
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Setup failed. Install Python 3.12 or later with PATH enabled, then retry.
pause
exit /b 1
