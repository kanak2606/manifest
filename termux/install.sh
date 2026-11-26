#!/data/data/com.termux/files/usr/bin/bash
# NoteTrace - Android Termux One-Click Installer
# Designed for Samsung tablets / ARM64 Android devices

set -e

echo "======================================================"
echo "    NoteTrace Android/Termux Installation Script     "
echo "======================================================"

# 1. Acquire wake lock during installation
if command -v termux-wake-lock >/dev/null 2>&1; then
    echo "[*] Acquiring Termux wake lock..."
    termux-wake-lock
fi

# 2. Setup storage access
echo "[*] Requesting Android shared storage access..."
if [ ! -d "$HOME/storage" ]; then
    termux-setup-storage || true
    echo "    (Please tap 'Allow' on your tablet when prompted)"
    sleep 2
fi

# 3. Update repositories and install required packages
echo "[*] Installing required packages (python, python-bcrypt, clang, git)..."
pkg update -y
pkg install -y python python-pip python-bcrypt git clang libffi openssl termux-tools

# 4. Create required directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "[*] Creating persistent data and log directories..."
mkdir -p data/uploads data/backups logs
mkdir -p "$HOME/storage/shared/NoteTrace/backups" 2>/dev/null || true

# 5. Create Python Virtual Environment (with system site packages for precompiled bcrypt)
echo "[*] Setting up Python virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    python -m venv --system-site-packages .venv
fi

source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# 6. Install Python dependencies with precompiled Termux wheels for Pydantic
echo "[*] Installing precompiled Pydantic for Android / Termux..."
pip install --extra-index-url https://termux-user-repository.github.io/pypi/ --only-binary=:all: pydantic

echo "[*] Installing remaining NoteTrace Python dependencies..."
pip install -r requirements.txt

# 7. Make helper scripts executable
echo "[*] Setting execution permissions on scripts..."
chmod +x termux/*.sh
chmod +x termux/boot/*.sh 2>/dev/null || true

# 8. Setup Termux:Boot auto-start if Termux:Boot directory exists
echo "[*] Configuring Termux:Boot auto-start..."
BOOT_DIR="$HOME/.termux/boot"
if [ -d "$BOOT_DIR" ] || [ -d "$HOME/.termux" ]; then
    mkdir -p "$BOOT_DIR"
    cp termux/boot/notetrace-boot.sh "$BOOT_DIR/notetrace-boot.sh"
    chmod +x "$BOOT_DIR/notetrace-boot.sh"
    echo "    -> Termux:Boot script installed to $BOOT_DIR/notetrace-boot.sh"
else
    echo "    -> Note: Termux:Boot addon not detected. If installed later, run:"
    echo "       mkdir -p ~/.termux/boot && cp termux/boot/notetrace-boot.sh ~/.termux/boot/"
fi

# 9. Determine device IP address on Wi-Fi
WLAN_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || echo "YOUR-TABLET-IP")

echo ""
echo "======================================================"
echo "          Installation Completed Successfully!        "
echo "======================================================"
echo ""
echo "To start NoteTrace right now, run:"
echo "    ./termux/start.sh"
echo ""
echo "Access Points:"
echo "  - Tablet NiKiosk Kiosk:  http://127.0.0.1:8000/display"
echo "  - Tablet Full UI:        http://127.0.0.1:8000"
echo "  - Laptop Wi-Fi Browser:  http://${WLAN_IP}:8000"
echo "======================================================"
