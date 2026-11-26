@echo off
title NoteTrace / Manifest - 1-Time SSH Key Setup
cls
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_ssh_key.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying with Windows PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_ssh_key.ps1"
)
echo.
pause
