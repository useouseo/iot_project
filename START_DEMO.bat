@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 goto finish
if not exist db_config.json if not defined RESTFLOW_DB_USER (
  py setup_mariadb.py
  if errorlevel 1 goto finish
)
py server.py --demo
:finish
pause
