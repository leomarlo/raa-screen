#!/usr/bin/env bash
# Wrapper that loads .env and launches the video agent with correct display auth.
set -euo pipefail

LOG=/tmp/video-agent-start.log
echo "[$(date)] start.sh invoked as $(whoami)" >> "$LOG"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env (export all vars)
set -a
# shellcheck source=.env
source "$SCRIPT_DIR/.env"
set +a

# Ensure X11 auth is available (needed when launched from systemd, not a desktop session)
if [ -z "${XAUTHORITY:-}" ]; then
    export XAUTHORITY="/home/$(whoami)/.Xauthority"
fi

# Wait for the X display to be ready (LightDM may not have started yet at boot)
echo "[$(date)] waiting for X display ${DISPLAY:-:0}..." >> "$LOG"
for i in $(seq 1 30); do
    if [ -e "/tmp/.X11-unix/X${DISPLAY#*:}" ] && [ -f "$XAUTHORITY" ]; then
        echo "[$(date)] X display ready after ${i}s" >> "$LOG"
        break
    fi
    sleep 1
done

# Kill any leftover processes and clean up lock files before starting
pkill -f cvlc      2>/dev/null || true
pkill -f vlc       2>/dev/null || true
pkill -f feh       2>/dev/null || true
pkill -f chromium  2>/dev/null || true
rm -f /tmp/vlc-*.lock 2>/dev/null || true
sleep 1

exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/video_agent.py"
