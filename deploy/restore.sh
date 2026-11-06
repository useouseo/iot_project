#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -ne 2 || "${2:-}" != '--confirm-replace' ]]; then
  echo 'Usage: sudo bash deploy/restore.sh BACKUP.sql.gz --confirm-replace' >&2
  echo 'This replaces the deployed restflow database. Take a backup first.' >&2
  exit 2
fi
archive="$(realpath -- "$1")"
[[ -f "$archive" ]] || { echo 'Backup file not found.' >&2; exit 1; }
gzip -t -- "$archive"
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
mkdir -p -- "$DEPLOY_DIR/.backups"
chmod 700 "$DEPLOY_DIR/.backups"
exec 9>"$DEPLOY_DIR/.backups/.lock"
flock -n 9 || { echo 'Another backup/restore is in progress.' >&2; exit 1; }
dc stop app
trap 'dc start app >/dev/null || true' EXIT
gzip -dc -- "$archive" | dc exec -T db mariadb --defaults-extra-file=/run/secrets/db_client
dc up -d --wait --wait-timeout 120 app
trap - EXIT
echo 'Database restored. Verify facilities, login and device reception.'
