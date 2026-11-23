@echo off
cd /d "%~dp0mobile"
if not exist .env.local (
  copy /y .env.example .env.local >nul
  echo Set the LAN server URL and TMAP demo key, save the file, then run START_APP.bat again.
  start "" notepad.exe ".env.local"
  pause
  exit /b 1
)
call npm.cmd ci
if errorlevel 1 goto finish
call npx.cmd expo start --go --lan
:finish
pause
