#!/usr/bin/env bash
#
# collector.sh - client-side diagnostic bundle collector (M2).
#
# Produces a bundle directory conforming to CONTRACT.md v1.0:
#
#   bundle-<machine_id>-<UTC YYYYMMDDTHHMMSSZ>/
#     manifest.json  system.txt  network.txt  processes.txt  packages.txt
#     services/<name>/{status.txt,journal.txt,config/}
#     app_logs/<name>.log
#     docs/**/*.md
#
# machine_id is the lowercase hostname sanitized to [a-z0-9-].
#
# Config discovery per service <name> (documented search path):
#   1. env-file candidates, first match wins: /etc/myapp/<name>.env (legacy),
#      /etc/clinic/<name>.env, /etc/clinic/<short-name>.env (namespaced units)
#   2. /etc/<name>/*              non-recursive; regular, readable, text files only
# Copies land under services/<name>/config/<original-filename>.
#
# Extra ad-hoc captures: set EXTRA_PATHS="/path/a.log /path/b.txt"
# (space-separated); each is captured as app_logs/<basename> (last 500 lines).
#
# Usage:
#   collector.sh [-o <outdir>] [--services "a b c"] [--docs <dir>]
#                [--push <brain-host>] [--notes "text"]
#
# Defaults: outdir ~/bundles, services "backend frontend",
# docs dir /opt/company-docs, no push, empty notes.
#
# Transport (CONTRACT.md section 5 / ADR-0003): without --push the bundle sits
# in <outdir> for SSH pull or USB carry; with --push it is scp'd into the
# Brain's inbox staging dir and atomically renamed into the inbox via ssh.
#
# Dependency-free: bash + coreutils. ip/ss/systemctl/journalctl/iptables/nft
# are all optional; a missing or failing command still gets its CMD marker
# followed by an "unavailable: <reason>" line. Safe to run as non-root.
# Individual command failures never abort the bundle.

set -u
set -o pipefail
shopt -s nullglob

CONTRACT_VERSION="1.0"
COLLECTOR_VERSION="1.0.0"
MAX_FILE_BYTES=524288      # 512 KB per-file cap (CONTRACT.md section 2)
MAX_BUNDLE_BYTES=5242880   # 5 MB total cap
MANIFEST_RESERVE=65536     # headroom for manifest.json within the total cap
MIN_SHRINK_BYTES=4096      # stop shrinking a file below this during budget pass

outdir="${HOME}/bundles"
services="backend frontend"
docs_dir="/opt/company-docs"
push_host=""
notes=""
EXTRA_PATHS="${EXTRA_PATHS:-}"

# Truncation bookkeeping. A newline-delimited list, not an associative array:
# macOS ships bash 3.2 and this script must run there (BSD userland generally -
# no GNU date -d, no find -printf; see the helpers below).
TRUNCATED_LIST=""
mark_truncated() { TRUNCATED_LIST="${TRUNCATED_LIST}${1}
"; }
is_truncated() { printf '%s' "$TRUNCATED_LIST" | grep -Fxq -- "$1"; }

usage() {
    cat <<'EOF'
Usage: collector.sh [-o <outdir>] [--services "a b c"] [--docs <dir>]
                    [--push <brain-host>] [--notes "text"]

  -o <outdir>        output directory for the bundle (default: ~/bundles)
  --services "a b"   space-separated service names (default: "backend frontend")
  --docs <dir>       docs corpus directory (default: /opt/company-docs)
  --push <host>      scp the bundle into <host>:~/brain/inbox/ (atomic deposit)
  --notes "text"     free-text note recorded in manifest.json

Env: EXTRA_PATHS="/path/a.log /path/b" - extra files captured under app_logs/.
EOF
}

warn() { printf 'collector: %s\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# --- argument parsing --------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        -o)         [ $# -ge 2 ] || { warn "missing value for -o"; exit 2; }
                    outdir=$2; shift 2 ;;
        --services) [ $# -ge 2 ] || { warn "missing value for --services"; exit 2; }
                    services=$2; shift 2 ;;
        --docs)     [ $# -ge 2 ] || { warn "missing value for --docs"; exit 2; }
                    docs_dir=$2; shift 2 ;;
        --push)     [ $# -ge 2 ] || { warn "missing value for --push"; exit 2; }
                    push_host=$2; shift 2 ;;
        --notes)    [ $# -ge 2 ] || { warn "missing value for --notes"; exit 2; }
                    notes=$2; shift 2 ;;
        -h|--help)  usage; exit 0 ;;
        *)          warn "unknown argument: $1"; usage >&2; exit 2 ;;
    esac
done

# --- helpers -----------------------------------------------------------------

file_size() {
    stat -c %s -- "$1" 2>/dev/null || wc -c <"$1" 2>/dev/null || printf '0'
}

# Text-file heuristic: empty files count as text; otherwise grep -I must match.
is_text_file() {
    [ -f "$1" ] && [ -r "$1" ] || return 1
    [ -s "$1" ] || return 0
    LC_ALL=C grep -qI . -- "$1" 2>/dev/null
}

# Bundle-internal path components must not contain ':' or newlines.
sanitize_relpath() {
    printf '%s' "$1" | tr ':' '-' | tr -d '\n'
}

json_escape() {
    local s=$1
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

# capture_cmd <outfile> <verbatim command string>
# Emits the CMD marker, then either the command's stdout or an
# "unavailable: <reason>" line. Returns 0 only when real output was written.
capture_cmd() {
    local outfile=$1 cmdstr=$2 first rc tmpo tmpe err
    printf '### CMD: %s ###\n' "$cmdstr" >>"$outfile"
    first=${cmdstr%% *}
    if ! have "$first"; then
        printf 'unavailable: %s not found\n' "$first" >>"$outfile"
        return 1
    fi
    tmpo=$(mktemp) || return 1
    tmpe=$(mktemp) || { rm -f "$tmpo"; return 1; }
    bash -c "$cmdstr" >"$tmpo" 2>"$tmpe"
    rc=$?
    if [ "$rc" -eq 0 ] || [ -s "$tmpo" ]; then
        cat "$tmpo" >>"$outfile"
        rm -f "$tmpo" "$tmpe"
        return 0
    fi
    err=$(head -n 1 "$tmpe" 2>/dev/null || true)
    printf 'unavailable: exit status %s%s\n' "$rc" "${err:+ ($err)}" >>"$outfile"
    rm -f "$tmpo" "$tmpe"
    return 1
}

# copy_text_file <src> <bundle-relative-dest>
copy_text_file() {
    local src=$1 rel=$2
    is_text_file "$src" || return 1
    case "$src" in *$'\n'*) return 1 ;; esac
    mkdir -p -- "$(dirname -- "$bundle_dir/$rel")"
    cp -- "$src" "$bundle_dir/$rel" 2>/dev/null
}

# --- bundle identity ---------------------------------------------------------

raw_hostname=$(hostname 2>/dev/null || uname -n 2>/dev/null || printf 'unknown')
machine_id=$(printf '%s' "$raw_hostname" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-')
[ -n "$machine_id" ] || machine_id="unknown"

mkdir -p -- "$outdir" || { warn "cannot create outdir $outdir"; exit 1; }

# Regenerate the timestamp until the directory name is free (idempotent reruns).
# Plain `date -u +FMT` only: GNU's `date -d @epoch` does not exist on BSD/macOS.
while :; do
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    bundle_id="bundle-${machine_id}-${ts}"
    bundle_dir="${outdir}/${bundle_id}"
    [ -e "$bundle_dir" ] || break
    sleep 1
done
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p -- "$bundle_dir" || { warn "cannot create $bundle_dir"; exit 1; }
warn "collecting into $bundle_dir"

# --- system.txt / network.txt / processes.txt / packages.txt -----------------

: >"$bundle_dir/system.txt"
capture_cmd "$bundle_dir/system.txt" "systemctl --failed" || true
capture_cmd "$bundle_dir/system.txt" "uptime" || true
capture_cmd "$bundle_dir/system.txt" "df -h" || true
capture_cmd "$bundle_dir/system.txt" "free -m" || true
capture_cmd "$bundle_dir/system.txt" "top -b -n 1 | head -30" || true

: >"$bundle_dir/network.txt"
capture_cmd "$bundle_dir/network.txt" "ip addr" || true
capture_cmd "$bundle_dir/network.txt" "ip route" || true
capture_cmd "$bundle_dir/network.txt" "ss -tlnp" || true
capture_cmd "$bundle_dir/network.txt" "cat /etc/resolv.conf" || true
if ! capture_cmd "$bundle_dir/network.txt" "iptables -L -n"; then
    capture_cmd "$bundle_dir/network.txt" "nft list ruleset" || true
fi

if have ps; then
    ps aux >"$bundle_dir/processes.txt" 2>/dev/null \
        || printf 'unavailable: ps aux failed\n' >"$bundle_dir/processes.txt"
else
    printf 'unavailable: ps not found\n' >"$bundle_dir/processes.txt"
fi

# packages.txt is optional; emit it only when package history is readable.
if [ -r /var/log/dpkg.log ]; then
    tail -n 200 /var/log/dpkg.log >"$bundle_dir/packages.txt" 2>/dev/null || true
elif [ -r /var/log/apt/history.log ]; then
    tail -n 200 /var/log/apt/history.log >"$bundle_dir/packages.txt" 2>/dev/null || true
fi

# --- services ----------------------------------------------------------------

for svc in $services; do
    svc=$(sanitize_relpath "$svc")
    [ -n "$svc" ] || continue
    svc_dir="$bundle_dir/services/$svc"
    mkdir -p -- "$svc_dir/config"

    unit_found=0
    status_out=""
    if have systemctl; then
        status_out=$(systemctl status "$svc" --no-pager -l 2>&1)
        status_rc=$?
        # rc 4 = no such unit; 0-3 = unit exists in some state.
        [ "$status_rc" -lt 4 ] && unit_found=1
    fi

    config_found=0
    # Env-file candidates: legacy /etc/myapp/<svc>.env, clinic-era /etc/clinic/<svc>.env,
    # and for namespaced units like clinic-backend also /etc/clinic/backend.env.
    svc_short=${svc#*-}
    for env_file in "/etc/myapp/$svc.env" "/etc/clinic/$svc.env" "/etc/clinic/$svc_short.env"; do
        if [ -f "$env_file" ] && copy_text_file "$env_file" "services/$svc/config/$(basename -- "$env_file")"; then
            config_found=1
            break
        fi
    done
    if [ -d "/etc/$svc" ]; then
        for cfg in "/etc/$svc"/*; do
            [ -f "$cfg" ] || continue
            if copy_text_file "$cfg" "services/$svc/config/$(sanitize_relpath "$(basename -- "$cfg")")"; then
                config_found=1
            fi
        done
    fi

    if [ "$unit_found" -eq 1 ]; then
        printf '%s\n' "$status_out" >"$svc_dir/status.txt"
        if have journalctl; then
            journal_out=$(journalctl -u "$svc" -n 200 --no-pager 2>&1)
            journal_rc=$?
            if [ "$journal_rc" -eq 0 ] || [ -n "$journal_out" ]; then
                printf '%s\n' "$journal_out" >"$svc_dir/journal.txt"
            else
                printf 'unavailable: journalctl exit status %s\n' "$journal_rc" >"$svc_dir/journal.txt"
            fi
        else
            printf 'unavailable: journalctl not found\n' >"$svc_dir/journal.txt"
        fi
    elif [ "$config_found" -eq 1 ]; then
        printf 'unavailable: no such systemd unit\n' >"$svc_dir/status.txt"
        printf 'unavailable: no such systemd unit\n' >"$svc_dir/journal.txt"
    else
        printf 'unavailable: no such service\n' >"$svc_dir/status.txt"
        printf 'unavailable: no such service\n' >"$svc_dir/journal.txt"
    fi
done

# --- app_logs ----------------------------------------------------------------

mkdir -p -- "$bundle_dir/app_logs"

# unique_app_log_path <basename> -> prints a free bundle-relative path
unique_app_log_path() {
    local base rel n
    base=$(sanitize_relpath "$1")
    [ -n "$base" ] || base="unnamed.log"
    rel="app_logs/$base"
    n=2
    while [ -e "$bundle_dir/$rel" ]; do
        rel="app_logs/${n}-${base}"
        n=$((n + 1))
    done
    printf '%s' "$rel"
}

capture_app_log() {
    local src=$1 rel
    [ -f "$src" ] || { warn "app log not found: $src"; return 1; }
    is_text_file "$src" || { warn "skipping binary/unreadable app log: $src"; return 1; }
    rel=$(unique_app_log_path "$(basename -- "$src")")
    tail -n 500 -- "$src" >"$bundle_dir/$rel" 2>/dev/null
}

for log in /var/log/myapp/*.log /var/log/clinic/*.log; do
    capture_app_log "$log" || true
done

for extra in $EXTRA_PATHS; do
    capture_app_log "$extra" || true
done

# --- docs --------------------------------------------------------------------

mkdir -p -- "$bundle_dir/docs"
if [ -d "$docs_dir" ]; then
    while IFS= read -r -d '' doc; do
        rel=${doc#"$docs_dir"/}
        copy_text_file "$doc" "docs/$(sanitize_relpath "$rel")" || true
    done < <(find "$docs_dir" -type f -name '*.md' -print0 2>/dev/null)
fi

# --- size caps ---------------------------------------------------------------

# Per-file cap: truncate from the top (keep the tail), record for the manifest.
while IFS= read -r -d '' f; do
    rel=${f#"$bundle_dir"/}
    sz=$(file_size "$f")
    if [ "$sz" -gt "$MAX_FILE_BYTES" ]; then
        tail -c "$MAX_FILE_BYTES" -- "$f" >"$f.trunc.tmp" && mv -- "$f.trunc.tmp" "$f"
        mark_truncated "$rel"
    fi
done < <(find "$bundle_dir" -type f -print0)

# Total cap: repeatedly halve the largest file until the bundle fits.
# file_size loops instead of `find -printf` (GNU-only; absent on BSD/macOS).
sized_files() {
    find "$bundle_dir" -type f | while IFS= read -r f; do
        printf '%s %s\n' "$(file_size "$f" | tr -d '[:space:]')" "${f#"$bundle_dir"/}"
    done
}
budget=$((MAX_BUNDLE_BYTES - MANIFEST_RESERVE))
while :; do
    total=$(sized_files | awk '{ s += $1 } END { print s + 0 }')
    [ "$total" -le "$budget" ] && break
    largest_size=""
    largest_rel=""
    read -r largest_size largest_rel < <(sized_files | sort -nr | head -n 1) || true
    if [ -z "${largest_rel:-}" ] || [ "${largest_size:-0}" -le "$MIN_SHRINK_BYTES" ]; then
        warn "cannot shrink bundle below $total bytes (budget $budget)"
        break
    fi
    tail -c "$((largest_size / 2))" -- "$bundle_dir/$largest_rel" >"$bundle_dir/$largest_rel.trunc.tmp" \
        && mv -- "$bundle_dir/$largest_rel.trunc.tmp" "$bundle_dir/$largest_rel"
    mark_truncated "$largest_rel"
done

# --- manifest.json -----------------------------------------------------------

os_name=$(. /etc/os-release 2>/dev/null && printf '%s' "${PRETTY_NAME:-}")
[ -n "$os_name" ] || os_name=$(uname -s 2>/dev/null || printf 'unknown')
kernel=$(uname -r 2>/dev/null || printf 'unknown')

{
    printf '{\n'
    printf '  "contract_version": "%s",\n' "$CONTRACT_VERSION"
    printf '  "bundle_id": "%s",\n' "$(json_escape "$bundle_id")"
    printf '  "machine_id": "%s",\n' "$(json_escape "$machine_id")"
    printf '  "hostname": "%s",\n' "$(json_escape "$raw_hostname")"
    printf '  "created_at": "%s",\n' "$created_at"
    printf '  "os": "%s",\n' "$(json_escape "$os_name")"
    printf '  "kernel": "%s",\n' "$(json_escape "$kernel")"
    printf '  "collector_version": "%s",\n' "$COLLECTOR_VERSION"
    printf '  "services": ['
    first=1
    for svc in $services; do
        svc=$(sanitize_relpath "$svc")
        [ -n "$svc" ] || continue
        [ "$first" -eq 1 ] || printf ', '
        printf '"%s"' "$(json_escape "$svc")"
        first=0
    done
    printf '],\n'
    printf '  "files": [\n'
    first=1
    while IFS= read -r f; do
        rel=${f#"$bundle_dir"/}
        [ -n "$rel" ] || continue
        bytes=$(file_size "$f" | tr -d '[:space:]')
        trunc="false"
        is_truncated "$rel" && trunc="true"
        [ "$first" -eq 1 ] || printf ',\n'
        printf '    {"path": "%s", "bytes": %s, "truncated": %s}' \
            "$(json_escape "$rel")" "$bytes" "$trunc"
        first=0
    done < <(find "$bundle_dir" -type f ! -name manifest.json | LC_ALL=C sort)
    printf '\n  ],\n'
    printf '  "notes": "%s"\n' "$(json_escape "$notes")"
    printf '}\n'
} >"$bundle_dir/manifest.json"

warn "bundle complete: $bundle_id ($(find "$bundle_dir" -type f | wc -l) files)"
printf '%s\n' "$bundle_dir"

# --- push mode (CONTRACT.md section 5, ADR-0003) -----------------------------

if [ -n "$push_host" ]; then
    if ! have scp || ! have ssh; then
        warn "push failed: scp/ssh not available; bundle left at $bundle_dir"
        exit 1
    fi
    if ! ssh "$push_host" 'mkdir -p brain/inbox/.staging'; then
        warn "push failed: cannot prepare staging dir on $push_host; bundle left at $bundle_dir"
        exit 1
    fi
    if ! scp -rq "$bundle_dir" "$push_host:brain/inbox/.staging/"; then
        warn "push failed: scp to $push_host failed; bundle left at $bundle_dir"
        exit 1
    fi
    if ! ssh "$push_host" "mv brain/inbox/.staging/$bundle_id brain/inbox/$bundle_id"; then
        warn "push failed: atomic rename on $push_host failed; bundle left in staging"
        exit 1
    fi
    warn "pushed to $push_host:~/brain/inbox/$bundle_id"
fi

exit 0
