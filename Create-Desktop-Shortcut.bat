@echo off
title Create Desktop Shortcut for Tablet Dev
cls
echo [*] Creating Desktop Shortcut for 1-Click Tablet Dev...
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"
if %ERRORLEVEL% NEQ 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"
)
echo.
pause
