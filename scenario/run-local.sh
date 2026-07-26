#!/usr/bin/env bash
# run-local.sh - start mock-db, backend, and frontend on one machine for
# development. Pidfiles and stdout/stderr logs land next to each server.
#
# Overrides (all optional):
#   MOCK_DB_PORT   mock-db listen port (default 5432; if you change it, also
#                  change DB_PORT in backend/backend.env to match)
#   FRONTEND_PORT  frontend listen port (default 8080)
#
# Stop everything with ./stop-local.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start_one() {
  local name="$1" dir="$2" pidfile="$2/$1.pid"
  shift 2
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "${name}: already running (pid $(cat "$pidfile"))"
    return 0
  fi
  # nohup must be a simple backgrounded command so $! is the real node pid,
  # not an intermediate subshell (env execs node, so the pid stays the same).
  (
    cd "$dir"
    nohup env "$@" node server.js >> "${name}.out.log" 2>&1 &
    echo $! > "$pidfile"
  )
  sleep 0.3
  if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "${name}: started (pid $(cat "$pidfile"))"
  else
    echo "${name}: FAILED to start; see ${dir}/${name}.out.log" >&2
    exit 1
  fi
}

start_one mock-db "${SCRIPT_DIR}/mock-db" MOCK_DB_PORT="${MOCK_DB_PORT:-5432}"
start_one backend "${SCRIPT_DIR}/backend" IGNORE_ME=1
start_one frontend "${SCRIPT_DIR}/frontend" PORT="${FRONTEND_PORT:-8080}"

echo
echo "port map: mock-db ${MOCK_DB_PORT:-5432}, backend 3001 (from backend.env), frontend ${FRONTEND_PORT:-8080}"
echo "open http://127.0.0.1:${FRONTEND_PORT:-8080}/ in a browser."
