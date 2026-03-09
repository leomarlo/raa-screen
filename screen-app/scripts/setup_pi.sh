#!/usr/bin/env bash
# Run ONCE on the Raspberry Pi to install deps and register the systemd service.
# Usage:  bash setup_pi.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"   # screen-app root
SERVICE_SRC="$APP_DIR/systemd/video-agent.service"
SERVICE_DST="/etc/systemd/system/video-agent.service"

echo "[1/5] Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y vlc feh python3-pip python3-venv
# chromium-browser is pre-installed on Raspberry Pi OS

echo "[2/5] Creating Python venv and installing deps..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[3/5] Setting up .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "  Created $APP_DIR/.env from example."
    echo "  Edit it now and set API_URL, then re-run or manually start the service."
    echo ""
fi

echo "[4/5] Installing systemd service..."
# Stop old @-style service if it exists
sudo systemctl stop "video-agent@leo.service" 2>/dev/null || true
sudo systemctl disable "video-agent@leo.service" 2>/dev/null || true
sudo rm -f "/etc/systemd/system/video-agent@leo.service"

sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable video-agent.service

echo "[5/5] Done."
echo ""
echo "Make sure $APP_DIR/.env has the correct API_URL, then start:"
echo "  sudo systemctl start video-agent.service"
echo ""
echo "Check logs:"
echo "  journalctl -u video-agent.service -f"
