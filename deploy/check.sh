#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
dc ps
# Read only the non-secret domain setting. Do not source .env as shell code.
domain="$(python3 - "$DEPLOY_DIR/.env" <<'PY'
from pathlib import Path
import sys
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.startswith('RESTFLOW_DOMAIN='):
        print(line.split('=',1)[1]);break
else:raise SystemExit('RESTFLOW_DOMAIN is missing')
PY
)"
curl --fail --silent --show-error --max-time 20 "https://$domain/api/health" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("ok") and d.get("demo") is False; print("HTTPS and live MariaDB health: OK")'
echo 'Next: sign in at /admin, generate QR, and scan with mobile data.'
