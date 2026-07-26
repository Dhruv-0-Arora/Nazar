#!/usr/bin/env bash
# Stages the two host layouts.
#
# The system does not live on one machine. A clinic host runs a built artifact
# and holds no source; the source repository lives on the build host. An
# engineer diagnosing a failure has to work across both — the error text is on
# one machine and the code that emits it is on the other.
#
#   scripts/deploy.sh prod  <dir>   artifact + config + logs. no source.
#   scripts/deploy.sh build <dir>   source repo + toolchain. no runtime config.
#
# Copy the resulting directory to the target machine, or point --target at a
# mounted path. Neither profile is a runnable checkout of the other.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-}"
DEST="${2:-}"

[ -n "$PROFILE" ] && [ -n "$DEST" ] || {
  echo "usage: deploy.sh <prod|build> <dir>" >&2; exit 1; }

case "$PROFILE" in prod|build) ;; *)
  echo "deploy.sh: profile must be 'prod' or 'build'" >&2; exit 1 ;; esac

mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"

# ------------------------------------------------------------------- prod ---
# What a clinic host actually has. Built bundles, machine config, log
# directory. No source, no node_modules, no package.json, no tooling.
if [ "$PROFILE" = "prod" ]; then
  [ -d "$ROOT/dist" ] || { echo "deploy.sh: dist/ missing — run scripts/build.sh first" >&2; exit 1; }

  mkdir -p "$DEST/opt/clinic" "$DEST/etc/clinic" "$DEST/var/log/clinic"
  cp -R "$ROOT/dist/." "$DEST/opt/clinic/"
  cp "$ROOT/backend/config/backend.env" "$DEST/etc/clinic/backend.env"

  # Point the config at the deployed paths rather than the working tree.
  tmp="$(mktemp)"
  sed -e "s|^LOG_FILE=.*|LOG_FILE=/var/log/clinic/backend.log|" \
      "$DEST/etc/clinic/backend.env" > "$tmp"
  cat "$tmp" > "$DEST/etc/clinic/backend.env"
  rm -f "$tmp"

  cat > "$DEST/opt/clinic/patients.json.README" <<'EOF'
Records file for clinic-mockdb. Sites on central records do not run this service.
EOF

  echo "staged prod layout at $DEST"
  echo "  opt/clinic/          backend.js portal.js mockdb.js public/ patients.json BUILD"
  echo "  etc/clinic/          backend.env"
  echo "  var/log/clinic/      (empty; filled at runtime)"
  echo
  echo "no source, no node_modules, no scripts."
  exit 0
fi

# ------------------------------------------------------------------ build ---
# What the build host has. Full source and toolchain, no runtime config and no
# logs — this machine never served a request.
mkdir -p "$DEST/srv/repo/clinic-services"
R="$DEST/srv/repo/clinic-services"

for d in backend frontend mockdb; do
  mkdir -p "$R/$d"
  cp -R "$ROOT/$d/." "$R/$d/"
done
cp "$ROOT/package.json" "$R/package.json"
[ -f "$ROOT/package-lock.json" ] && cp "$ROOT/package-lock.json" "$R/"
mkdir -p "$R/scripts"
cp "$ROOT/scripts/build.sh" "$R/scripts/build.sh"

# The runtime config belongs to the machine, not the repo. What a build host
# carries is the committed example.
if [ -f "$R/backend/config/backend.env" ]; then
  mv "$R/backend/config/backend.env" "$R/backend/config/backend.env.example"
fi

cat > "$R/.gitignore" <<'EOF'
node_modules/
dist/
*.log
.local/
EOF

echo "staged build layout at $DEST"
echo "  srv/repo/clinic-services/   backend/ frontend/ mockdb/ scripts/build.sh package.json"
echo "  backend/config/             backend.env.example  (not the live config)"
echo
echo "no runtime config, no logs, no artifact."
echo
echo "note: run scripts/nuke.sh against this directory before collection —"
echo "      the repo still carries internal tooling and documentation."
