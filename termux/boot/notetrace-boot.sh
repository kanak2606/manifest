#!/data/data/com.termux/files/usr/bin/bash
# NoteTrace - Termux:Boot Startup Script
# Automatically launches NoteTrace when the Samsung tablet boots up

# Wait 10 seconds for Android network stack and Wi-Fi to initialize
sleep 10

# Acquire Termux wake lock immediately
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
fi

# Locate NoteTrace directory
POSSIBLE_DIRS=(
    "$HOME/NoteTrace"
    "$HOME/notetrace"
    "$HOME/projects/notetrace"
    "$HOME/storage/shared/NoteTrace"
)

TARGET_DIR=""
for d in "${POSSIBLE_DIRS[@]}"; do
    if [ -f "$d/termux/start.sh" ]; then
        TARGET_DIR="$d"
        break
    fi
done

if [ -n "$TARGET_DIR" ]; then
    echo "[*] Auto-starting NoteTrace from $TARGET_DIR..." >> "$HOME/notetrace-boot.log"
    bash "$TARGET_DIR/termux/start.sh" >> "$HOME/notetrace-boot.log" 2>&1
else
    echo "[!] Could not locate NoteTrace directory in boot script." >> "$HOME/notetrace-boot.log"
fi
