#!/data/data/com.termux/files/usr/bin/bash
# NoteTrace - Automated Database & Media Backup Script for Android / Termux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="notetrace_backup_${TIMESTAMP}.tar.gz"
TEMP_DIR="/tmp/notetrace_backup_${TIMESTAMP}"
LOCAL_BACKUP_DIR="$SCRIPT_DIR/data/backups"
ANDROID_BACKUP_DIR="$HOME/storage/shared/NoteTrace/backups"

mkdir -p "$LOCAL_BACKUP_DIR"
mkdir -p "$ANDROID_BACKUP_DIR" 2>/dev/null || true
mkdir -p "$TEMP_DIR"

echo "[*] Starting NoteTrace backup ($TIMESTAMP)..."

# 1. Perform safe online SQLite backup using Python's built-in sqlite3 backup API
DB_FILE="$SCRIPT_DIR/data/notetrace.db"
if [ -f "$DB_FILE" ]; then
    echo "    Backing up SQLite database..."
    python -c "import sqlite3; s = sqlite3.connect('$DB_FILE'); d = sqlite3.connect('$TEMP_DIR/notetrace.db'); s.backup(d); s.close(); d.close()"
fi

# 2. Copy uploads if they exist
if [ -d "$SCRIPT_DIR/data/uploads" ]; then
    echo "    Backing up uploaded attachments and images..."
    cp -r "$SCRIPT_DIR/data/uploads" "$TEMP_DIR/uploads"
fi

# 3. Create compressed tarball
echo "    Compressing backup archive..."
tar -czf "$LOCAL_BACKUP_DIR/$BACKUP_NAME" -C "$TEMP_DIR" .
rm -rf "$TEMP_DIR"

# 4. Copy to Android persistent storage (accessible in Samsung Files / SD Card)
if [ -d "$ANDROID_BACKUP_DIR" ]; then
    cp "$LOCAL_BACKUP_DIR/$BACKUP_NAME" "$ANDROID_BACKUP_DIR/$BACKUP_NAME"
    echo "[✓] Backup saved to Android Shared Storage: $ANDROID_BACKUP_DIR/$BACKUP_NAME"
fi

echo "[✓] Backup saved to Local Data: $LOCAL_BACKUP_DIR/$BACKUP_NAME"

# 5. Rotate old backups: keep latest 14
echo "[*] Cleaning up old backups (keeping latest 14)..."
ls -1t "$LOCAL_BACKUP_DIR"/notetrace_backup_*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
if [ -d "$ANDROID_BACKUP_DIR" ]; then
    ls -1t "$ANDROID_BACKUP_DIR"/notetrace_backup_*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
fi

echo "[✓] Backup process complete."
