#!/usr/bin/env bash
# Run from your Mac to push screen-app to the Pi and restart the service.
# Usage:
#   bash deploy_scp.sh                          # uses defaults below
#   PI_HOST=192.168.1.42 PI_USER=leo bash deploy_scp.sh
set -euo pipefail

PI_HOST="${PI_HOST:-raspberrypi.local}"
PI_USER="${PI_USER:-leo}"
REMOTE_DIR="/home/${PI_USER}/screen-app"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"   # screen-app root

echo "[1/3] Syncing files to ${PI_USER}@${PI_HOST}:${REMOTE_DIR} ..."
rsync -avz --progress \
    --exclude='.env' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$APP_DIR/" \
    "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/"

echo "[2/3] Updating Python deps on Pi..."
ssh "${PI_USER}@${PI_HOST}" "
    cd ${REMOTE_DIR}
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
"

echo "[3/3] Restarting service..."
ssh "${PI_USER}@${PI_HOST}" "
    sudo systemctl restart video-agent.service
    sudo systemctl status video-agent.service --no-pager
"

echo "Done. Tail logs with:"
echo "  ssh ${PI_USER}@${PI_HOST} journalctl -u video-agent.service -f"
