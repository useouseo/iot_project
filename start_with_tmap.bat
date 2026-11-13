@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

REM 아래 두 줄의 = 뒤에 발급받은 앱 키를 입력하고 저장하세요.
REM 한 키에 지도와 보행자 API 권한이 있으면 두 줄에 같은 키를 넣습니다.
set "RESTFLOW_TMAP_MAP_KEY="
set "RESTFLOW_TMAP_ROUTE_KEY="

if not defined RESTFLOW_TMAP_MAP_KEY goto missing_key
if not defined RESTFLOW_TMAP_ROUTE_KEY goto missing_key
if not exist "%~dp0start_public_demo.bat" goto missing_project
call "%~dp0start_public_demo.bat"
exit /b %errorlevel%

:missing_key
echo.
echo 이 파일을 메모장으로 열고 두 개의 KEY= 뒤에 앱 키를 입력한 후 저장하세요.
echo 설정 후 이 파일을 더블클릭하면 실행됩니다.
echo 앱 키가 들어간 파일은 GitHub에 올리거나 공유하지 마세요.
pause
exit /b 1

:missing_project
echo.
echo 이 파일을 start_public_demo.bat와 같은 프로젝트 폴더에 넣어주세요.
pause
exit /b 1
