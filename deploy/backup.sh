#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
umask 077
BACKUP_DIR="$DEPLOY_DIR/.backups"
mkdir -p -- "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.lock"
flock -n 9 || { echo 'Another backup/restore is in progress.' >&2; exit 1; }
temporary="$(mktemp "$BACKUP_DIR/.backup.XXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
filename="$BACKUP_DIR/restflow-$(date -u +%Y%m%dT%H%M%S%NZ).sql.gz"
dc exec -T db mariadb-dump --defaults-extra-file=/run/secrets/db_client \
  --single-transaction --quick --routines --events --add-drop-database --databases restflow \
  | gzip > "$temporary"
gzip -t -- "$temporary"
mv -- "$temporary" "$filename"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'restflow-*.sql.gz' -mtime +14 -delete
printf 'Backup saved: %s\n' "$filename"
