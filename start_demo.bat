@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist "db_config.json" (
  echo.
  echo MariaDB first-time setup will start now.
  .venv\Scripts\python.exe setup_mariadb.py
  if errorlevel 1 goto db_failed
)
echo.
echo Open http://localhost:8000 in your browser after the server starts.
echo Admin page: http://localhost:8000/admin
echo Sign in with your admin password.
echo Keep this window open. Press Ctrl+C to stop the server.
echo.
.venv\Scripts\python.exe server.py --demo %*
if errorlevel 1 goto server_failed
pause
exit /b 0
:server_failed
echo.
echo Server did not start. Close the OLD server window with Ctrl+C and retry.
echo If port 8000 is in use, you can also run: start_demo.bat --port 8001
pause
exit /b 1
:db_failed
echo.
echo MariaDB setup failed. Start the MariaDB service and check the account information.
echo Run .venv\Scripts\python.exe setup_mariadb.py to retry.
pause
exit /b 1
:failed
echo.
echo Setup failed. Install Python 3.12 or later with PATH enabled, then retry.
pause
exit /b 1
