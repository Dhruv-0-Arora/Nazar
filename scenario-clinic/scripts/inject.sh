#!/usr/bin/env bash
# inject.sh — plant the outage.
#
# Rewrites DB_HOST in the backend's environment file to a host that no longer
# resolves, then restarts the service. The service comes back up clean and
# reports active (running); every patient lookup fails.
#
# IDEMPOTENT. Safe to run twice — re-running re-asserts the broken value rather
# than stacking edits, and the pristine backup is only taken once.
#
#   scripts/inject.sh                    # default bug: stale DB_HOST
#   scripts/inject.sh --bug empty-env    # DB_HOST set but empty
#   scripts/inject.sh --bug bad-port     # right host, dead port
#   scripts/inject.sh --bug malformed-db # corrupt the records JSON
#   scripts/inject.sh --dry-run
#
# Env overrides for local testing (defaults are the deployed paths):
#   ENV_FILE=/etc/clinic/backend.env
#   SERVICE=clinic-backend
#   DATA_FILE=/opt/clinic/mockdb/patients.json

set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/clinic/backend.env}"
SERVICE="${SERVICE:-clinic-backend}"
DATA_FILE="${DATA_FILE:-/opt/clinic/mockdb/patients.json}"
BACKUP="${ENV_FILE}.pristine"
DATA_BACKUP="${DATA_FILE}.pristine"

BUG="stale-host"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --bug) BUG="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "inject.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

say() { printf '[inject] %s\n' "$*"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[inject] DRY-RUN would: %s\n' "$*"
  else
    "$@"
  fi
}

# Rewrite KEY=value in place, appending the key if it is absent.
set_env_key() {
  local key="$1" value="$2" file="$3"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[inject] DRY-RUN would set %s=%s in %s\n' "$key" "$value" "$file"
    return
  fi
  if grep -qE "^${key}=" "$file"; then
    # No sed -i portability games: rewrite via a temp file.
    local tmp
    tmp="$(mktemp)"
    sed "s|^${key}=.*|${key}=${value}|" "$file" > "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

restart_service() {
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "${SERVICE}.service" >/dev/null 2>&1; then
    say "restarting ${SERVICE} via systemd"
    run systemctl restart "$SERVICE"
  else
    say "systemd not managing ${SERVICE} — restart it yourself for the change to take effect"
    say "  (local dev: Ctrl-C scripts/run-local.sh and start it again)"
  fi
}

[ -f "$ENV_FILE" ] || { echo "inject.sh: $ENV_FILE not found. Set ENV_FILE=… for local testing." >&2; exit 1; }

# Backup once, and only from a known-clean file. Running inject twice must not
# overwrite the pristine copy with an already-broken one.
if [ ! -f "$BACKUP" ]; then
  say "saving pristine config to $BACKUP"
  run cp "$ENV_FILE" "$BACKUP"
else
  say "pristine backup already exists, leaving it alone"
fi

case "$BUG" in
  stale-host)
    # The decommissioned-host bug. DNS fails -> ENOTFOUND on every lookup.
    say "setting DB_HOST=db-primary.cedarhollow.internal (decommissioned, does not resolve)"
    set_env_key DB_HOST "db-primary.cedarhollow.internal" "$ENV_FILE"
    ;;
  empty-env)
    say "setting DB_HOST= (present but empty) -> ECONFIG"
    set_env_key DB_HOST "" "$ENV_FILE"
    ;;
  bad-port)
    say "setting DB_PORT=5433 (nothing listening) -> ECONNREFUSED"
    set_env_key DB_PORT "5433" "$ENV_FILE"
    ;;
  malformed-db)
    say "corrupting $DATA_FILE -> upstream 500, backend reports EHTTP500"
    [ -f "$DATA_FILE" ] || { echo "inject.sh: $DATA_FILE not found. Set DATA_FILE=…" >&2; exit 1; }
    [ -f "$DATA_BACKUP" ] || run cp "$DATA_FILE" "$DATA_BACKUP"
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '[inject] DRY-RUN would truncate JSON in %s\n' "$DATA_FILE"
    else
      # Lop off the closing braces: valid-looking file, invalid JSON.
      head -c $(( $(wc -c < "$DATA_FILE") - 40 )) "$DATA_BACKUP" > "$DATA_FILE"
    fi
    ;;
  *)
    echo "inject.sh: unknown bug '$BUG' (stale-host|empty-env|bad-port|malformed-db)" >&2
    exit 2
    ;;
esac

restart_service

say "injected: $BUG"
say "expected symptom chain:"
say "  systemctl status $SERVICE  -> active (running)"
say "  curl :8080/healthz         -> 200 ok"
say "  curl :8080/api/patients    -> 502"
say "  app log                    -> ERROR ... records database unreachable"
