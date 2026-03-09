#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/video-resource-api"

echo "[1/5] Updating apt + installing prerequisites..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

echo "[2/5] Installing Docker (official repo)..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  ${UBUNTU_CODENAME} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[3/5] Enabling Docker..."
systemctl enable --now docker

echo "[4/5] Creating app directory: ${APP_DIR} ..."
mkdir -p "${APP_DIR}"
chown -R root:root "${APP_DIR}"
chmod 755 "${APP_DIR}"

echo "[5/5] Done."
echo "Next:"
echo "  - Put your repo in ${APP_DIR}"
echo "  - Create ${APP_DIR}/.env"
echo "  - Run: cd ${APP_DIR} && docker compose up -d --build"
