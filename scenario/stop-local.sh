#!/usr/bin/env bash
# stop-local.sh - stop the locally started mock-db, backend, and frontend.
# Idempotent: missing pidfiles or dead processes are fine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_one() {
  local name="$1" pidfile="$2/$1.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "${name}: not running (no pidfile)"
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
    echo "${name}: stopped (pid ${pid})"
  else
    echo "${name}: already dead (stale pidfile)"
  fi
  rm -f "$pidfile"
}

stop_one frontend "${SCRIPT_DIR}/frontend"
stop_one backend "${SCRIPT_DIR}/backend"
stop_one mock-db "${SCRIPT_DIR}/mock-db"
