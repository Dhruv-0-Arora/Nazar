#!/usr/bin/env bash
# revert.sh - restore health: point the backend back at the local database
# (DB_HOST=127.0.0.1) and restart the backend. Demo reset tool.
#
# Idempotent: safe to run twice; the DB_HOST line is replaced in place.
# Hand-authored, never produced by the Brain (see ADR-0010).
#
# Modes:
#   ./revert.sh            local mode: edits scenario/backend/backend.env,
#                          restarts via scenario/backend/backend.pid if present
#   ./revert.sh --system   system mode: edits /etc/myapp/backend.env and runs
#                          `systemctl restart backend` (needs sudo)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD_HOST="127.0.0.1"

set_db_host() {
  local file="$1" host="$2"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: env file not found: $file" >&2
    exit 1
  fi
  if grep -q '^DB_HOST=' "$file"; then
    sed -i "s/^DB_HOST=.*/DB_HOST=${host}/" "$file"
  else
    printf 'DB_HOST=%s\n' "$host" >> "$file"
  fi
  echo "set DB_HOST=${host} in ${file}"
}

restart_local_backend() {
  local backend_dir="${SCRIPT_DIR}/backend"
  local pidfile="${backend_dir}/backend.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "no pidfile at ${pidfile}; backend not restarted."
    echo "start it yourself, e.g.:  cd ${backend_dir} && nohup node server.js >> backend.out.log 2>&1 & echo \$! > backend.pid"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
  # nohup must be a simple backgrounded command so $! is the real node pid,
  # and the pidfile path must be absolute (the subshell's cwd is backend_dir).
  (
    cd "$backend_dir"
    nohup node server.js >> backend.out.log 2>&1 &
    echo $! > "$pidfile"
  )
  echo "backend restarted (pid $(cat "$pidfile"))"
}

if [[ "${1:-}" == "--system" ]]; then
  if [[ ! -w /etc/myapp/backend.env ]]; then
    echo "ERROR: /etc/myapp/backend.env not writable; run with sudo." >&2
    exit 1
  fi
  set_db_host /etc/myapp/backend.env "$GOOD_HOST"
  systemctl restart backend
  echo "backend service restarted (systemctl)."
else
  set_db_host "${SCRIPT_DIR}/backend/backend.env" "$GOOD_HOST"
  restart_local_backend
fi

echo "health restored: backend points at ${GOOD_HOST} again."
