#!/data/data/com.termux/files/usr/bin/bash
# NoteTrace - Graceful Server Shutdown Script for Termux / Android

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/notetrace.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[!] No PID file found ($PID_FILE). Is NoteTrace running?"
    # Fallback: check if python run.py is active
    PIDS=$(pgrep -f "python run.py" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "[*] Killing remaining NoteTrace python processes: $PIDS"
        kill -15 $PIDS 2>/dev/null || true
    fi
else
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[*] Stopping NoteTrace server (PID: $PID)..."
        kill -15 "$PID"
        
        # Wait up to 5 seconds for graceful shutdown
        for i in {1..5}; do
            if kill -0 "$PID" 2>/dev/null; then
                sleep 1
            else
                break
            fi
        done
        
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "[!] Server didn't exit gracefully; sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        echo "[✓] NoteTrace server stopped."
    else
        echo "[!] NoteTrace process $PID was not running."
    fi
    rm -f "$PID_FILE"
fi

# Release Termux wake lock if no other instances running
if command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock
    echo "[*] Termux wake lock released."
fi
