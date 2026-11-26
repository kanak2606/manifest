#!/data/data/com.termux/files/usr/bin/bash
# NoteTrace - Background Startup Script for Termux / Android

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/notetrace.pid"
LOG_FILE="$SCRIPT_DIR/logs/notetrace.log"

# Prevent multiple instances
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[!] NoteTrace is already running with PID $PID."
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# 1. Acquire Android wake lock so Termux does not sleep when screen is off
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
    echo "[*] Termux wake lock acquired (screen/background persistence enabled)."
fi

# 2. Activate virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# 3. Create log directory
mkdir -p "$SCRIPT_DIR/logs"

# 4. Launch NoteTrace server in the background
PORT="${PORT:-8000}"
export PORT
echo "[*] Launching NoteTrace Python FastAPI server on 0.0.0.0:${PORT}..."
nohup python run.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

sleep 1

# Verify startup
if kill -0 "$SERVER_PID" 2>/dev/null; then
    WLAN_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || echo "TABLET_IP")
    echo "[✓] NoteTrace started successfully (PID: $SERVER_PID)"
    echo ""
    echo "======================================================"
    echo "  Live Endpoints:"
    echo "   - Tablet NiKiosk Display: http://127.0.0.1:${PORT}/display"
    echo "   - Tablet Editor:          http://127.0.0.1:${PORT}"
    echo "   - Windows Laptop Access:  http://${WLAN_IP}:${PORT}"
    echo "======================================================"
    echo "  Log output: $LOG_FILE"
    echo "  To stop:    ./termux/stop.sh"
else
    echo "[X] NoteTrace failed to start. Last log lines:"
    tail -n 20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
