#!/usr/bin/env bash
# Run only on the purchased Ubuntu 24.04 VPS, with source at /opt/restflow.
set -euo pipefail
if [[ "$EUID" -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$DEPLOY_DIR" != /opt/restflow/deploy ]]; then
  echo 'Place this project at /opt/restflow first.' >&2; exit 1
fi
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
  echo 'This installer supports Ubuntu 24.04 LTS.' >&2; exit 1
fi
if [[ "$#" -ne 4 || "$1" != '--domain' || "$3" != '--email' ]]; then
  echo 'Usage: sudo bash deploy/install.sh --domain restflow.example.com --email you@example.com' >&2
  exit 2
fi
apt-get update
apt-get install -y docker.io docker-compose-v2 python3 curl gzip util-linux
systemctl enable --now docker
python3 "$DEPLOY_DIR/configure.py" --domain "$2" --email "$4"
source "$DEPLOY_DIR/common.sh"
dc up -d --build --wait --wait-timeout 240
install -m 644 "$DEPLOY_DIR/restflow-backup.service" /etc/systemd/system/restflow-backup.service
install -m 644 "$DEPLOY_DIR/restflow-backup.timer" /etc/systemd/system/restflow-backup.timer
systemctl daemon-reload
systemctl enable --now restflow-backup.timer
bash "$DEPLOY_DIR/backup.sh"
echo 'Containers started and daily backup enabled.'
echo 'After DNS points to this server and TCP 80/443 are allowed, run:'
echo 'sudo bash /opt/restflow/deploy/check.sh'
echo 'Check completion requires a valid public HTTPS URL; startup alone does not verify it.'
