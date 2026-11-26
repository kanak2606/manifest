@echo off
title NoteTrace / Manifest - Tablet Dev Center
cls
cd /d "%~dp0"

where pwsh >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\tablet_control.ps1" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\tablet_control.ps1" %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Session closed with exit code %ERRORLEVEL%.
    pause
)
