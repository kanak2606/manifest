@echo off
cd /d "%~dp0"

echo ===================================================
echo              Manifest Local Server
echo ===================================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    python -m venv .venv
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Ensuring dependencies are installed...
python -m pip install -r requirements.txt --quiet

echo.
echo ===================================================
echo  Manifest is ready and running!
echo  - Full App:    http://localhost:8000
echo  - Kiosk Mode:  http://localhost:8000/display
echo ===================================================
echo.
echo Press Ctrl+C to stop.
echo.

python run.py
pause
