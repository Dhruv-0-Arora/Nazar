#!/usr/bin/env bash
# revert.sh — restore the system to healthy and let the demo run again cleanly.
#
# Restores from the .pristine backups inject.sh made, then restarts the service.
# IDEMPOTENT. Running it on an already-healthy system is a no-op.
#
#   scripts/revert.sh
#   scripts/revert.sh --dry-run
#
# Env overrides match inject.sh:
#   ENV_FILE=/etc/clinic/backend.env
#   SERVICE=clinic-backend
#   DATA_FILE=/opt/clinic/mockdb/patients.json
#
# NOTE: this is the reference fix, kept for demo resets. It is NOT the artifact
# the Brain produces — the autofix milestone has the agent write its own revert
# from the diagnosis. Don't hand this file to the agent.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/clinic/backend.env}"
SERVICE="${SERVICE:-clinic-backend}"
DATA_FILE="${DATA_FILE:-/opt/clinic/mockdb/patients.json}"
BACKUP="${ENV_FILE}.pristine"
DATA_BACKUP="${DATA_FILE}.pristine"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

say() { printf '[revert] %s\n' "$*"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[revert] DRY-RUN would: %s\n' "$*"
  else
    "$@"
  fi
}

restored=0

if [ -f "$BACKUP" ]; then
  say "restoring $ENV_FILE from $BACKUP"
  run cp "$BACKUP" "$ENV_FILE"
  run rm -f "$BACKUP"
  restored=1
else
  say "no config backup at $BACKUP — config already clean"
fi

if [ -f "$DATA_BACKUP" ]; then
  say "restoring $DATA_FILE from $DATA_BACKUP"
  run cp "$DATA_BACKUP" "$DATA_FILE"
  run rm -f "$DATA_BACKUP"
  restored=1
else
  say "no data backup at $DATA_BACKUP — records file already clean"
fi

if [ "$restored" -eq 0 ]; then
  say "nothing to revert, system is already in its pristine state"
  exit 0
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "${SERVICE}.service" >/dev/null 2>&1; then
  say "restarting ${SERVICE} via systemd"
  run systemctl restart "$SERVICE"
else
  say "systemd not managing ${SERVICE} — restart it yourself for the change to take effect"
fi

say "reverted"
say "verify:  curl :8080/api/patients  -> 200 with 12 records"
