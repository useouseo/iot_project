#!/usr/bin/env bash
set -euo pipefail
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
  echo 'Run deploy/configure.py first.' >&2
  exit 1
fi
COMPOSE_ARGS=(--project-directory "$DEPLOY_DIR" --env-file "$DEPLOY_DIR/.env" -f "$DEPLOY_DIR/compose.yaml")
if [[ -n "${RESTFLOW_COMPOSE_PROJECT:-}" ]]; then
  COMPOSE_ARGS+=(-p "$RESTFLOW_COMPOSE_PROJECT")
fi
dc() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }
