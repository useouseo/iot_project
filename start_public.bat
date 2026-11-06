@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
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
.venv\Scripts\python.exe tools\public_start.py %*
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Setup or startup failed. See the error above.
echo Python 3.12 and a running MariaDB service are required.
echo If mariadb_config is missing, install MariaDB Connector/C or use Python 3.12 64-bit.
pause
exit /b 1
