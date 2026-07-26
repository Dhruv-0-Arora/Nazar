#!/usr/bin/env bash
# main.sh — the ONE script the FDE runs on the sick client machine.
#
# First run (no collect.conf yet): starts setup.sh, which registers the
# problem folders / logs / services and then AUTOMATICALLY runs collector.sh,
# leaving a contract-v1 bundle in outbox/ on this stick.
#
# Later runs (collect.conf exists): skips setup and re-runs collection
# straight away, producing a fresh bundle.
#
#   ./main.sh                          interactive setup (first run) or collect
#   ./main.sh --problem-dir D --log F  non-interactive setup + collect
#   ./main.sh --reconfigure [...]      force setup again even if configured
#
# Any other arguments are passed through to setup.sh (see setup.sh --help).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$SCRIPT_DIR/collect.conf"

RECONFIGURE=0
ARGS=()
for a in "$@"; do
    case "$a" in
        --reconfigure) RECONFIGURE=1 ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) ARGS+=("$a") ;;
    esac
done

if [ ! -f "$CONF" ] || [ $RECONFIGURE -eq 1 ] || [ ${#ARGS[@]} -gt 0 ]; then
    echo "==> No configuration found (or reconfigure requested): running setup."
    echo "    Collection starts automatically when setup completes."
    exec bash "$SCRIPT_DIR/setup.sh" ${ARGS[@]+"${ARGS[@]}"}
else
    echo "==> Found $CONF - setup already done, collecting now."
    exec bash "$SCRIPT_DIR/collector.sh" --conf "$CONF"
fi
