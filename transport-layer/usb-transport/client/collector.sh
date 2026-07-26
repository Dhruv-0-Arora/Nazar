#!/usr/bin/env bash
# collector.sh — build a diagnostic bundle per CONTRACT.md (contract v1).
#
# Dependency-free bash. Runs on the sick client machine. Reads the targets
# registered by setup.sh (collect.conf), captures system/network state, tails
# the registered logs, copies the registered problem folder(s), and writes a
# manifest.json describing every file in the bundle. The bundle lands in
# outbox/ next to this script — which, when this folder lives on a USB stick,
# means the bundle is already on the stick.
#
# Never runs automatically. A human invokes it.

COLLECTOR_VERSION="0.1.0"
CONTRACT_VERSION="1"

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$SCRIPT_DIR/collect.conf"
OUTBOX="$SCRIPT_DIR/outbox"

usage() {
    cat <<'EOF'
Usage: collector.sh [--conf FILE] [--outbox DIR]

Builds bundle-<hostname>-<timestamp>/ inside the outbox from the targets
registered in collect.conf (created by setup.sh).

  --conf FILE    config file to use (default: collect.conf next to this script)
  --outbox DIR   where to write the bundle (default: outbox/ next to this script)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --conf)   CONF="$2"; shift 2 ;;
        --outbox) OUTBOX="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

if [ ! -f "$CONF" ]; then
    echo "ERROR: config not found: $CONF" >&2
    echo "Run ./setup.sh first to register your problem folder and log files." >&2
    exit 1
fi

# Defaults; collect.conf overrides.
PROBLEM_DIRS=()
LOG_FILES=()
SERVICES=()
DOCS_DIR=""
LOG_TAIL_LINES=500
MAX_FILE_BYTES=5242880

# shellcheck disable=SC1090
. "$CONF"

# ---------------------------------------------------------------- helpers ---

# Safe expansion of possibly-empty arrays under `set -u` on older bash.
problem_dirs() { printf '%s\n' ${PROBLEM_DIRS[@]+"${PROBLEM_DIRS[@]}"}; }

json_escape() {
    local s=$1
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    printf '%s' "$s"
}

# capture <outfile> <command...>  — append delimited command output per contract.
capture() {
    local out=$1; shift
    local cmd="$*"
    local first=${cmd%% *}
    {
        printf '### CMD: %s ###\n' "$cmd"
        if command -v "$first" >/dev/null 2>&1; then
            bash -c "$cmd" 2>&1
            local rc=$?
            [ $rc -ne 0 ] && printf '[exit status %d]\n' "$rc"
        else
            printf '[command not available on this system]\n'
        fi
        printf '\n'
    } >> "$out"
}

note() { printf '%s\n' "$1" >> "$BUNDLE_DIR/NOTES.txt"; }

file_bytes() { wc -c < "$1" | tr -d '[:space:]'; }

# ---------------------------------------------------------------- prepare ---

HOST_RAW="$(hostname 2>/dev/null || echo unknown-host)"
HOST="$(printf '%s' "$HOST_RAW" | tr -c 'A-Za-z0-9._-' '-')"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OS_DESC="$(uname -srm 2>/dev/null || echo unknown-os)"

BUNDLE_NAME="bundle-${HOST}-${TS}"
BUNDLE_DIR="$OUTBOX/$BUNDLE_NAME"

if [ -e "$BUNDLE_DIR" ]; then
    echo "ERROR: $BUNDLE_DIR already exists (two runs in one second?). Retry." >&2
    exit 1
fi
mkdir -p "$BUNDLE_DIR"
: > "$BUNDLE_DIR/NOTES.txt"

echo "==> Building $BUNDLE_NAME"
echo "    collector v$COLLECTOR_VERSION, contract v$CONTRACT_VERSION"

# ------------------------------------------------------- system + network ---

echo "==> Capturing system state (missing commands are noted, not fatal)"
SYS="$BUNDLE_DIR/system.txt"
capture "$SYS" "uname -a"
capture "$SYS" "uptime"
capture "$SYS" "df -h"
capture "$SYS" "free -m"
capture "$SYS" "systemctl --failed --no-pager"
capture "$SYS" "ps aux"

echo "==> Capturing network state"
NET="$BUNDLE_DIR/network.txt"
capture "$NET" "ip addr"
capture "$NET" "ip route"
capture "$NET" "ss -tlnp"
capture "$NET" "netstat -an"
capture "$NET" "cat /etc/resolv.conf"
capture "$NET" "iptables -S"
capture "$NET" "ipconfig /all"

# --------------------------------------------------------------- services ---

for svc in ${SERVICES[@]+"${SERVICES[@]}"}; do
    echo "==> Capturing service: $svc"
    d="$BUNDLE_DIR/services/$svc"
    mkdir -p "$d"
    capture "$d/status.txt"  "systemctl status $svc --no-pager"
    capture "$d/journal.txt" "journalctl -u $svc -n 200 --no-pager"
done

# --------------------------------------------------------------- app logs ---

mkdir -p "$BUNDLE_DIR/app_logs"
SOURCES="$BUNDLE_DIR/app_logs/SOURCES.txt"
: > "$SOURCES"
i=0
for lf in ${LOG_FILES[@]+"${LOG_FILES[@]}"}; do
    i=$((i + 1))
    if [ -r "$lf" ]; then
        base="$(basename "$lf")"
        dest="app_logs/$(printf '%02d' "$i")-$base"
        total_lines="$(wc -l < "$lf" | tr -d '[:space:]')"
        tail -n "$LOG_TAIL_LINES" "$lf" > "$BUNDLE_DIR/$dest"
        truncated="no"
        [ "$total_lines" -gt "$LOG_TAIL_LINES" ] && truncated="yes"
        printf '%s <- %s (source %s lines, kept last %s, truncated=%s)\n' \
            "$dest" "$lf" "$total_lines" "$LOG_TAIL_LINES" "$truncated" >> "$SOURCES"
        echo "==> Log captured: $lf ($total_lines lines, truncated=$truncated)"
    else
        printf 'MISSING <- %s (not readable at collection time)\n' "$lf" >> "$SOURCES"
        note "WARNING: registered log not readable: $lf"
        echo "==> WARNING: log not readable, skipped: $lf"
    fi
done

# ---------------------------------------------------------- problem dirs ----

mkdir -p "$BUNDLE_DIR/problem"
SKIPPED="$BUNDLE_DIR/problem/SKIPPED.txt"
: > "$SKIPPED"
for pd in ${PROBLEM_DIRS[@]+"${PROBLEM_DIRS[@]}"}; do
    pd="${pd%/}"
    if [ ! -d "$pd" ]; then
        note "WARNING: registered problem dir missing: $pd"
        echo "==> WARNING: problem dir missing, skipped: $pd"
        continue
    fi
    base="$(basename "$pd")"
    echo "==> Copying problem folder: $pd"
    copied=0
    while IFS= read -r -d '' f; do
        rel="${f#"$pd"/}"
        bytes="$(file_bytes "$f")"
        if [ "$bytes" -gt "$MAX_FILE_BYTES" ]; then
            printf '%s (%s bytes > cap %s)\n' "$pd/$rel" "$bytes" "$MAX_FILE_BYTES" >> "$SKIPPED"
            continue
        fi
        mkdir -p "$BUNDLE_DIR/problem/$base/$(dirname "$rel")"
        cp "$f" "$BUNDLE_DIR/problem/$base/$rel"
        copied=$((copied + 1))
    done < <(find "$pd" -type f -print0)
    echo "    $copied file(s) copied"
done

# ------------------------------------------------------------------- docs ---

if [ -n "$DOCS_DIR" ]; then
    if [ -d "$DOCS_DIR" ]; then
        echo "==> Copying docs corpus: $DOCS_DIR"
        mkdir -p "$BUNDLE_DIR/docs"
        cp -R "${DOCS_DIR%/}"/. "$BUNDLE_DIR/docs/"
    else
        note "WARNING: registered docs dir missing: $DOCS_DIR"
    fi
fi

# --------------------------------------------------------------- manifest ---

echo "==> Generating manifest.json"

if command -v sha256sum >/dev/null 2>&1; then
    SHA_TOOL="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
    SHA_TOOL="shasum -a 256"
else
    SHA_TOOL=""
    note "WARNING: no sha256 tool on this system; manifest hashes are empty"
fi

kind_of() {
    case "$1" in
        system.txt)          echo system ;;
        network.txt)         echo network ;;
        NOTES.txt)           echo meta ;;
        app_logs/SOURCES.txt) echo meta ;;
        app_logs/*)          echo log ;;
        services/*)          echo service ;;
        problem/SKIPPED.txt) echo meta ;;
        problem/*)           echo problem ;;
        docs/*)              echo knowledge ;;
        *)                   echo other ;;
    esac
}

# Pre-pass: one line per file "rel|bytes|sha256|kind" so totals are known
# before the JSON is emitted.
INDEX_TMP="$(mktemp)"
trap 'rm -f "$INDEX_TMP"' EXIT
total_bytes=0
file_count=0
while IFS= read -r -d '' f; do
    rel="${f#"$BUNDLE_DIR"/}"
    [ "$rel" = "manifest.json" ] && continue
    bytes="$(file_bytes "$f")"
    if [ -n "$SHA_TOOL" ]; then
        hash="$($SHA_TOOL "$f" | awk '{print $1}')"
    else
        hash=""
    fi
    kind="$(kind_of "$rel")"
    printf '%s|%s|%s|%s\n' "$rel" "$bytes" "$hash" "$kind" >> "$INDEX_TMP"
    total_bytes=$((total_bytes + bytes))
    file_count=$((file_count + 1))
done < <(find "$BUNDLE_DIR" -type f -print0 | sort -z)

json_str_array() {  # emit "a","b",... for the given args
    local first=1 item
    for item in "$@"; do
        [ $first -eq 0 ] && printf ', '
        printf '"%s"' "$(json_escape "$item")"
        first=0
    done
}

MANIFEST="$BUNDLE_DIR/manifest.json"
{
    printf '{\n'
    printf '  "contract_version": "%s",\n'  "$CONTRACT_VERSION"
    printf '  "collector_version": "%s",\n' "$COLLECTOR_VERSION"
    printf '  "bundle": "%s",\n'            "$(json_escape "$BUNDLE_NAME")"
    printf '  "hostname": "%s",\n'          "$(json_escape "$HOST")"
    printf '  "created_at_utc": "%s",\n'    "$CREATED_AT"
    printf '  "os": "%s",\n'                "$(json_escape "$OS_DESC")"
    printf '  "targets": {\n'
    printf '    "problem_dirs": [%s],\n' "$(json_str_array ${PROBLEM_DIRS[@]+"${PROBLEM_DIRS[@]}"})"
    printf '    "log_files": [%s],\n'    "$(json_str_array ${LOG_FILES[@]+"${LOG_FILES[@]}"})"
    printf '    "docs_dir": "%s",\n'     "$(json_escape "$DOCS_DIR")"
    printf '    "services": [%s]\n'      "$(json_str_array ${SERVICES[@]+"${SERVICES[@]}"})"
    printf '  },\n'
    printf '  "log_tail_lines": %s,\n' "$LOG_TAIL_LINES"
    printf '  "file_count": %s,\n'     "$file_count"
    printf '  "total_bytes": %s,\n'    "$total_bytes"

    # counts_by_kind
    printf '  "counts_by_kind": {'
    cut -d'|' -f4 "$INDEX_TMP" | sort | uniq -c | {
        first=1
        while read -r count kind; do
            [ $first -eq 0 ] && printf ', '
            printf '"%s": %s' "$kind" "$count"
            first=0
        done
    }
    printf '},\n'

    # files array
    printf '  "files": [\n'
    first=1
    while IFS='|' read -r rel bytes hash kind; do
        [ $first -eq 0 ] && printf ',\n'
        printf '    {"path": "%s", "bytes": %s, "sha256": "%s", "kind": "%s"}' \
            "$(json_escape "$rel")" "$bytes" "$hash" "$kind"
        first=0
    done < "$INDEX_TMP"
    printf '\n  ]\n'
    printf '}\n'
} > "$MANIFEST"

# ---------------------------------------------------------------- summary ---

echo
echo "=============================================================="
echo " Bundle ready: $BUNDLE_DIR"
echo "   files: $file_count   total: $total_bytes bytes"
echo
echo " Next step (USB mode): eject this drive, plug it into the"
echo " workstation (Brain), and run (no arguments needed):"
echo "   python <stick>/usb-transport/workstation/receive_bundle.py"
echo
echo " Next step (SSH mode): from the Brain, run pull.sh against"
echo " this machine; it fetches manifest.json first, then the bundle."
echo "=============================================================="
