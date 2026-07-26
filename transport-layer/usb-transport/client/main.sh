#!/usr/bin/env bash
# main.sh — the ONE script the FDE runs on the sick client machine.
#
# Configuration is PER DEVICE: each machine gets its own
# collect-<machine_id>.conf on this stick, so carrying the stick across
# several laptops runs setup once on each NEW device and collects
# immediately on devices already set up. Bundles from every device
# accumulate side by side in outbox/.
#
# First run on a device: starts setup.sh, which registers the problem
# folders / logs / services and then AUTOMATICALLY runs collector.sh,
# leaving a contract-v1 bundle in outbox/ on this stick.
#
# Later runs on the same device: skips setup, collects straight away.
#
#   ./main.sh                          interactive setup (first run) or collect
#   ./main.sh --problem-dir D --log F  non-interactive setup + collect
#   ./main.sh --reconfigure [...]      redo setup for THIS device
#
# Any other arguments are passed through to setup.sh (see setup.sh --help).
# NAZAR_MACHINE_ID=<id> overrides the hostname (useful for dry-runs).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Same machine_id derivation as collector.sh (CONTRACT.md section 1).
machine_id() {
    local raw
    raw="${NAZAR_MACHINE_ID:-$(hostname 2>/dev/null || echo unknown-host)}"
    printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/--*/-/g; s/^-//; s/-$//'
}
MID="$(machine_id)"
[ -n "$MID" ] || MID="unknown-host"
CONF="$SCRIPT_DIR/collect-$MID.conf"

RECONFIGURE=0
ARGS=()
for a in "$@"; do
    case "$a" in
        --reconfigure) RECONFIGURE=1 ;;
        -h|--help)
            sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) ARGS+=("$a") ;;
    esac
done

if [ -f "$SCRIPT_DIR/collect.conf" ] && [ ! -f "$CONF" ]; then
    echo "NOTE: legacy shared collect.conf found - ignored (configs are per-device now)."
fi

if [ ! -f "$CONF" ] || [ $RECONFIGURE -eq 1 ] || [ ${#ARGS[@]} -gt 0 ]; then
    echo "==> No configuration for device '$MID' (or reconfigure requested): running setup."
    echo "    Collection starts automatically when setup completes."
    exec bash "$SCRIPT_DIR/setup.sh" ${ARGS[@]+"${ARGS[@]}"}
else
    echo "==> Found $CONF - device '$MID' already set up, collecting now."
    exec bash "$SCRIPT_DIR/collector.sh" --conf "$CONF"
fi
