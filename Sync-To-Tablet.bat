@echo off
title Manifest / NoteTrace - Package, Push, Deploy and Service Manager
cls
cd /d "%~dp0"

echo ========================================================
echo  Manifest / NoteTrace - Tablet Deployment and Services
echo ========================================================
echo.
echo  Port Architecture:
echo   * 5000-Series (Remote Dev Tools):
echo     - SSH Service   : Port 5022
echo     - Code-Server   : Port 5080 (http://[tablet-ip]:5080)
echo   * 8000-Series (Deployments and Web Apps):
echo     - NoteTrace App : Port 8000 (http://[tablet-ip]:8000)
echo.
echo  [1] Full Auto: Package + Push + Cache Clear + Restart (Port 8000)
echo  [2] Deploy Only: Package + Push + Cache Clear (Do Not Restart)
echo  [3] Restart Services Only (on Tablet, Port 8000)
echo  [4] Start Services Only   (on Tablet, Port 8000)
echo  [5] Stop Services Only    (on Tablet)
echo.

set "choice=%1"
if "%choice%"=="" (
    set /p choice="Select an option [1-5, default 1]: "
)
if "%choice%"=="" set choice=1

:: Normalize text inputs / aliases
if /i "%choice%"=="restart"    set choice=3
if /i "%choice%"=="-restart"   set choice=3
if /i "%choice%"=="--restart"  set choice=3
if /i "%choice%"=="start"      set choice=4
if /i "%choice%"=="-start"     set choice=4
if /i "%choice%"=="--start"    set choice=4
if /i "%choice%"=="stop"       set choice=5
if /i "%choice%"=="-stop"      set choice=5
if /i "%choice%"=="--stop"     set choice=5
if /i "%choice%"=="deploy"     set choice=2
if /i "%choice%"=="-norestart" set choice=2

echo.
set "PS_ARGS="
if "%choice%"=="2" set "PS_ARGS=-NoRestart"
if "%choice%"=="3" set "PS_ARGS=-RestartOnly"
if "%choice%"=="4" set "PS_ARGS=-StartOnly"
if "%choice%"=="5" set "PS_ARGS=-StopOnly"

where pwsh >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_to_tablet.ps1" %PS_ARGS%
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_to_tablet.ps1" %PS_ARGS%
)

echo.
echo ========================================================
echo  Process complete. Press any key to close this window.
echo ========================================================
pause >nul
