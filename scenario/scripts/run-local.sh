#!/usr/bin/env bash
# Runs all three services on one machine for development.
#
# This is NOT the demo topology — on demo day mockdb+backend live on one laptop
# and the portal on another, each under systemd. This script exists so the
# scenario can be built and the symptom chain verified without two laptops.
#
#   scripts/run-local.sh          start (reads .local/backend.env)
#   scripts/run-local.sh --fresh  discard .local/backend.env and start clean
#
# The backend reads its config from .local/backend.env, seeded from
# backend/config/backend.env on first run. That mirrors systemd's
# EnvironmentFile= and means inject.sh / revert.sh work locally:
#
#   ENV_FILE=.local/backend.env scripts/inject.sh    # break it
#   (restart this script)                            # systemd would do this for you
#   ENV_FILE=.local/backend.env scripts/revert.sh    # fix it
#
# Ctrl-C stops everything.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL="$ROOT/.local"
ENV_FILE="$LOCAL/backend.env"
LOG_DIR="$LOCAL/logs"

mkdir -p "$LOG_DIR"

if [ "${1:-}" = "--fresh" ]; then
  rm -f "$ENV_FILE" "$ENV_FILE.pristine"
  echo "discarded local config"
fi

if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/backend/config/backend.env" "$ENV_FILE"
  # The deployed log path needs root; keep local runs in the working tree.
  tmp="$(mktemp)"
  sed "s|^LOG_FILE=.*|LOG_FILE=$LOG_DIR/backend.log|" "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
  echo "seeded $ENV_FILE from backend/config/backend.env"
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

echo "config   $ENV_FILE"
echo "DB_HOST  ${DB_HOST:-(unset)}:${DB_PORT:-(unset)}"
echo "logs     $LOG_DIR/backend.log"

pids=()
cleanup() {
  echo
  echo "stopping…"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

MOCKDB_PORT=5432 node "$ROOT/mockdb/server.js" &
pids+=($!)

# DB_HOST/DB_PORT/PORT/LOG_FILE all come from the sourced env file above, which
# is the point — inject.sh edits that file and this picks the change up on the
# next start, exactly as a systemd restart would.
node "$ROOT/backend/server.js" &
pids+=($!)

SERVICE_NAME=clinic-portal \
PORT=3000 \
BACKEND_URL=http://127.0.0.1:8080 \
node "$ROOT/frontend/server.js" &
pids+=($!)

sleep 1
echo
echo "portal   http://127.0.0.1:3000"
echo "backend  http://127.0.0.1:8080/api/patients"
echo
wait
