#!/usr/bin/env bash
#
#   ███ NUKE ███   scorched-earth hint removal
#
# Strips a deployed copy of the scenario down to what a real broken production
# box would actually look like: no scripts that name the bug, no backups holding
# the pristine value, no docs describing the symptom chain, and no source
# comments explaining that any of this is a scenario.
#
# WHY THIS EXISTS: the honest test is whether the agent can diagnose the outage
# from evidence. If inject.sh, BREAKAGE.md, or a comment reading "this is the
# whole point of the scenario" is sitting on the box, the agent isn't
# diagnosing — it's reading the answer sheet. Nuke first, then evaluate.
#
# THIS DELETES FILES IRREVERSIBLY. Run it on a DEPLOYED COPY, never on the
# source repo. It refuses to run inside the source tree unless forced.
#
#   scripts/nuke.sh --target /opt/clinic            # dry run, lists everything
#   scripts/nuke.sh --target /opt/clinic --yes      # arm it, then type NUKE
#   scripts/nuke.sh --target /opt/clinic --verify   # audit only, changes nothing
#
# Exit codes: 0 clean · 1 usage/refusal · 2 verify found surviving hints

set -euo pipefail

TARGET=""
MODE="dry"

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --yes)    MODE="arm"; shift ;;
    --verify) MODE="verify"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "nuke: unknown argument '$1'" >&2; exit 1 ;;
  esac
done

[ -n "$TARGET" ] || { echo "nuke: --target <dir> is required. Refusing to guess." >&2; exit 1; }
[ -d "$TARGET" ] || { echo "nuke: '$TARGET' is not a directory." >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

# Filenames that exist only to explain the scenario.
HINT_FILES=(
  "DETAILS.md"
  "BREAKAGE.md"
  "README.md"
  "ground_truth.md"
  "placement.json"
  "CONTRACT.md"
  "scripts/inject.sh"
  "scripts/revert.sh"
  "scripts/run-local.sh"
  "scripts/nuke.sh"
)

# Left alone: ordinary service documentation that names no fault and describes
# no tooling. A box with zero docs reads as tampered-with; this is what a real
# internal repo looks like.
KEEP_FILES=( "mockdb/README.md" )

# Deleted, then rewritten as ordinary documentation. Their presence afterwards is
# expected, so verify checks their *contents* (via the keyword grep) rather than
# their existence.
REGENERATED=( "README.md" )

# Anything matching these is a leak: backups reveal the pristine value, dev
# artifacts reveal the healthy state, .git reveals the entire authoring history.
HINT_GLOBS=( "*.pristine" "*.orig" "*.bak" ".runlog" )
HINT_DIRS=( ".git" ".local" "node_modules" )

# Words that should never appear in a file on a client box. Used both to scrub
# comments and to verify afterwards.
KEYWORDS='scenario|inject\.sh|revert\.sh|ground.?truth|symptom chain|on purpose|deliberate|by design|the whole point|the point of|demo day|hackathon|war room|FDE|give the bug away|BREAKAGE|nuke'

banner() {
  echo
  echo "  ███ NUKE ███  target: $TARGET"
  echo "  mode: $MODE"
  echo
}

# ---------------------------------------------------------------- verify ----
# Prints every surviving hint. Exit 2 if any found. Changes nothing.
verify() {
  local failures=0

  echo "── files that should not exist ──"
  local found_files=0
  for f in "${HINT_FILES[@]}"; do
    local regenerated=0
    for r in "${REGENERATED[@]}"; do [ "$f" = "$r" ] && regenerated=1; done
    [ "$regenerated" -eq 1 ] && continue
    [ -e "$TARGET/$f" ] && { echo "  LEAK  $f"; found_files=1; }
  done
  for g in "${HINT_GLOBS[@]}"; do
    while IFS= read -r hit; do
      echo "  LEAK  ${hit#$TARGET/}"; found_files=1
    done < <(find "$TARGET" -name "$g" 2>/dev/null)
  done
  for d in "${HINT_DIRS[@]}"; do
    [ -e "$TARGET/$d" ] && { echo "  LEAK  $d/"; found_files=1; }
  done
  [ "$found_files" -eq 0 ] && echo "  clean" || failures=1

  echo
  echo "── scenario language in file contents ──"
  local content_hits
  content_hits="$(grep -rnEI "$KEYWORDS" "$TARGET" 2>/dev/null || true)"
  if [ -n "$content_hits" ]; then
    printf '%s\n' "$content_hits" | sed "s|$TARGET/|  LEAK  |" | head -40
    local n
    n="$(printf '%s\n' "$content_hits" | wc -l | tr -d ' ')"
    [ "$n" -gt 40 ] && echo "  … and $((n - 40)) more"
    failures=1
  else
    echo "  clean"
  fi

  echo
  echo "── the bug itself must SURVIVE ──"
  # A nuke that also removes the fault leaves nothing to diagnose. Check the
  # config is present and that DB_HOST is still pointing somewhere.
  local cfg
  cfg="$(find "$TARGET" -name 'backend.env' -print -quit 2>/dev/null || true)"
  [ -z "$cfg" ] && [ -f /etc/clinic/backend.env ] && cfg=/etc/clinic/backend.env
  if [ -n "$cfg" ]; then
    echo "  ok    config present: ${cfg#$TARGET/}"
    if grep -qE '^DB_HOST=.+' "$cfg"; then
      echo "  ok    DB_HOST set: $(grep -E '^DB_HOST=' "$cfg")"
    else
      echo "  note  DB_HOST empty or absent — consistent with the empty-env fault"
    fi
  else
    echo "  WARN  no backend.env found — nothing left to diagnose?"
  fi

  echo
  if [ "$failures" -ne 0 ]; then
    echo "  RESULT: FAIL — hints survive. The agent would be reading the answer."
    return 2
  fi
  echo "  RESULT: PASS — nothing left but evidence."
  return 0
}

# ---------------------------------------------------------------- scrub -----
# Drops comment lines and block comments that contain scenario language, from
# .js/.sh/.json files. Deliberately conservative: only touches comments.
scrub_comments() {
  local dry="$1"
  node - "$TARGET" "$dry" <<'NODE'
const fs = require('fs'), path = require('path');
const [root, dry] = process.argv.slice(2);
const DRY = dry === 'dry';
const RE = /scenario|inject\.sh|revert\.sh|ground.?truth|symptom chain|on purpose|deliberate|by design|the whole point|the point of|demo day|hackathon|war room|FDE|give the bug away|BREAKAGE|nuke/i;
// Every text format that ships to a client box and can carry a comment.
// Missing one here is how a hint survives — verify() is the backstop.
const EXT = new Set([
  '.js', '.mjs', '.cjs', '.sh', '.bash',
  '.css', '.html',
  '.env', '.conf', '.service', '.ini',
  '.yaml', '.yml', '.toml',
]);
let touched = 0;

function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (!e.name.startsWith('.')) walk(p); continue; }
    if (!EXT.has(path.extname(e.name))) continue;

    const src = fs.readFileSync(p, 'utf8');
    const lines = src.split('\n');
    const keep = [];
    let inBlock = false, block = [];

    for (const line of lines) {
      const t = line.trim();
      if (!inBlock && (t.startsWith('/**') || t.startsWith('/*')) && !t.includes('*/')) {
        inBlock = true; block = [line]; continue;
      }
      if (inBlock) {
        block.push(line);
        if (t.includes('*/')) {
          inBlock = false;
          if (!RE.test(block.join('\n'))) keep.push(...block);
          block = [];
        }
        continue;
      }
      // Whole-line // or # comments only. Never touches code with a trailing
      // comment, so nothing executable can break.
      if ((t.startsWith('//') || (t.startsWith('#') && !t.startsWith('#!'))) && RE.test(t)) continue;
      keep.push(line);
    }
    if (inBlock) keep.push(...block);

    const out = keep.join('\n');
    if (out !== src) {
      touched++;
      console.log(`  ${DRY ? 'would scrub' : 'scrubbed  '}  ${path.relative(root, p)}`);
      if (!DRY) fs.writeFileSync(p, out);
    }
  }
}
walk(root);
if (!touched) console.log('  no comment leaks found');
NODE
}

# ---------------------------------------------------------------- plan ------
plan() {
  echo "── would delete ──"
  local any=0
  for f in "${HINT_FILES[@]}"; do [ -e "$TARGET/$f" ] && { echo "  rm  $f"; any=1; }; done
  for g in "${HINT_GLOBS[@]}"; do
    while IFS= read -r hit; do echo "  rm  ${hit#$TARGET/}"; any=1; done < <(find "$TARGET" -name "$g" 2>/dev/null)
  done
  for d in "${HINT_DIRS[@]}"; do [ -e "$TARGET/$d" ] && { echo "  rm -rf  $d/"; any=1; }; done
  [ "$any" -eq 0 ] && echo "  nothing to delete"
  echo
  echo "── would scrub comments from ──"
  scrub_comments dry
  echo
  echo "── would restore ordinary documentation ──"
  write_production_readme dry
  echo
  echo "── would keep ──"
  for f in "${KEEP_FILES[@]}"; do [ -e "$TARGET/$f" ] && echo "  keep  $f"; done
}

# Replaces the internal README with plain operations documentation. A repo with
# no README at all looks emptied-out; this leaves something an on-call engineer
# would expect to find. Names no fault and describes no tooling.
write_production_readme() {
  local dry="$1"
  if [ "$dry" = "dry" ]; then
    echo "  would write  README.md  (operations documentation)"
    return
  fi
  cat > "$TARGET/README.md" <<'EOF'
# clinic-services

Patient records stack for Cedar Hollow Community Health site clinics.
Three Node services, standard library only — no dependencies, no build step.

| Service | Port | Role |
|---|---|---|
| `clinic-mockdb` | 5432 | Records service. See `mockdb/README.md`. |
| `clinic-backend` | 8080 | Patient API consumed by the portal. |
| `clinic-portal` | 3000 | Browser UI for front-desk and clinical staff. |

## Configuration

`clinic-backend` reads `/etc/clinic/backend.env` (systemd `EnvironmentFile=`):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | Listen port |
| `BIND` | `0.0.0.0` | Listen address |
| `DB_HOST` | — | Records service hostname |
| `DB_PORT` | `5432` | Records service port |
| `DB_TIMEOUT_MS` | `3000` | Upstream request timeout |
| `LOG_FILE` | `/var/log/clinic/backend.log` | Application log path |

`clinic-portal` reads `BACKEND_URL` and serves it to the browser at
`/config.json`. Site clinics point this at their own backend host.

## Endpoints

`clinic-backend`

| Path | Returns |
|---|---|
| `/healthz` | Liveness. Does not check upstreams. |
| `/api/meta` | Version, pid, uptime, configured upstream, last successful read |
| `/api/patients` | Patient records; `?q=` filters on name or MRN |

A `502 records_database_unreachable` means the backend is up but could not
reach the records service. The response body carries the error class, the
upstream host and port it dialled, and a correlation ID. The same three values
are written to the application log on the same line.

## Operations

```bash
systemctl status clinic-backend
journalctl -u clinic-backend -n 200
tail -f /var/log/clinic/backend.log
```

`/healthz` reports process liveness only. It returns 200 whenever the service is
running, including while upstreams are unavailable — check `/api/meta` or the
application log to confirm records access.

Configuration changes require a service restart:

```bash
systemctl restart clinic-backend
```

## Logs

One line per event: ISO 8601 timestamp, level, service name, message, then
`key=value` fields. Failed lookups record `cid`, `err`, `upstream`, and `ms`.
Match `cid` against the correlation ID shown in the portal to tie a staff report
to a specific request.

## Data handling

Patient records stay on the clinic network. No service in this stack makes
outbound requests beyond its configured upstream.
EOF
  echo "  wrote  README.md  (operations documentation)"
}

execute() {
  echo "── deleting ──"
  for f in "${HINT_FILES[@]}"; do [ -e "$TARGET/$f" ] && { rm -f "$TARGET/$f"; echo "  rm  $f"; }; done
  for g in "${HINT_GLOBS[@]}"; do find "$TARGET" -name "$g" -exec rm -f {} + 2>/dev/null || true; done
  for d in "${HINT_DIRS[@]}"; do [ -e "$TARGET/$d" ] && { rm -rf "${TARGET:?}/$d"; echo "  rm -rf  $d/"; }; done
  # An empty scripts/ is its own tell — something clearly used to live there.
  [ -d "$TARGET/scripts" ] && rmdir "$TARGET/scripts" 2>/dev/null && echo "  rmdir   scripts/"
  echo
  echo "── scrubbing comments ──"
  scrub_comments wet
  echo
  echo "── restoring ordinary documentation ──"
  write_production_readme wet
  echo
  echo "── verifying ──"
  verify
}

banner

case "$MODE" in
  verify) verify; exit $? ;;
  dry)
    plan
    echo
    echo "  Dry run. Nothing was changed."
    echo "  To actually do it:  $0 --target $TARGET --yes"
    exit 0
    ;;
esac

# ------------------------------------------------------------ double check --
# Guard 1: refuse to detonate inside a source checkout. scripts/build.sh and
# package.json exist only in the repository; a deployment produced by deploy.sh
# has neither, and a checkout sits under a git work tree. Nuking the checkout
# would destroy the work for everyone.
if [ -e "$TARGET/scripts/build.sh" ] || [ -e "$TARGET/package.json" ] \
   || [ -d "$TARGET/.git" ] || [ -d "$TARGET/../.git" ]; then
  echo "  REFUSING: '$TARGET' looks like a source checkout, not a deployed copy."
  echo "  Run scripts/deploy.sh first, then nuke the deployment. Source stays intact."
  exit 1
fi

# Guard 2: typed confirmation. --yes alone is not enough.
echo "  About to permanently delete the files listed above and rewrite comments."
echo "  There is no undo and no backup."
echo
printf '  Type NUKE to confirm: '
read -r reply
if [ "$reply" != "NUKE" ]; then
  echo "  Aborted. Nothing was changed."
  exit 1
fi
echo

execute
