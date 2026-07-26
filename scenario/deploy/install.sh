#!/usr/bin/env bash
# Installs the scenario onto a clinic laptop under systemd.
#
#   sudo ./deploy/install.sh laptop-a
#   sudo ./deploy/install.sh laptop-b http://<laptop-a-ip>:8080
#
# laptop-a runs clinic-mockdb + clinic-backend and holds the backend config.
# laptop-b runs clinic-portal and points at laptop-a.
#
# Deploys the BUILT artifact from dist/, not source. Run scripts/build.sh first.
# Copies each laptop's corpus docs per corpus/placement.json.
# Never copies ground_truth.md or placement.json onto a laptop.

set -euo pipefail

ROLE="${1:-}"
BACKEND_URL="${2:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$ROLE" in
  laptop-a|laptop-b) ;;
  *) echo "usage: install.sh <laptop-a|laptop-b> [backend-url]" >&2; exit 1 ;;
esac

[ "$(id -u)" -eq 0 ] || { echo "install.sh: needs root (writes /opt, /etc, /var/log)" >&2; exit 1; }
[ -d "$ROOT/dist" ] || { echo "install.sh: dist/ missing - run scripts/build.sh first" >&2; exit 1; }

install -d /opt/clinic /etc/clinic /var/log/clinic /opt/company-docs

echo "installing artifact to /opt/clinic"
cp -R "$ROOT/dist/." /opt/clinic/

# ---------------------------------------------------------------- corpus ----
# Each laptop gets only its own doc set. The doc explaining the fault lives on
# the opposite machine from the fault, so diagnosis requires both bundles.
echo "installing corpus docs for $ROLE"
node -e '
const fs = require("fs"), path = require("path");
const [root, role] = process.argv.slice(1);
const placement = JSON.parse(fs.readFileSync(path.join(root, "corpus/placement.json"), "utf8"));
for (const doc of placement[role] || []) {
  fs.copyFileSync(path.join(root, "corpus", doc), path.join("/opt/company-docs", doc));
  console.log("  " + doc);
}
' "$ROOT" "$ROLE"

# Belt and braces: the grading key and the placement map must never reach a
# client machine, whatever else this script does.
rm -f /opt/company-docs/ground_truth.md /opt/company-docs/placement.json

if [ "$ROLE" = "laptop-a" ]; then
  echo "installing backend config to /etc/clinic/backend.env"
  cp "$ROOT/backend/config/backend.env" /etc/clinic/backend.env
  sed -i 's|^LOG_FILE=.*|LOG_FILE=/var/log/clinic/backend.log|' /etc/clinic/backend.env

  install -m 644 "$ROOT/deploy/clinic-mockdb.service" /etc/systemd/system/
  install -m 644 "$ROOT/deploy/clinic-backend.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now clinic-mockdb clinic-backend
  systemctl --no-pager status clinic-backend | head -5
else
  [ -n "$BACKEND_URL" ] || { echo "install.sh: laptop-b needs a backend URL" >&2; exit 1; }
  echo "installing portal config to /etc/clinic/portal.env"
  cat > /etc/clinic/portal.env <<EOF
SERVICE_NAME=clinic-portal
PORT=3000
BACKEND_URL=$BACKEND_URL
EOF

  install -m 644 "$ROOT/deploy/clinic-portal.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now clinic-portal
  systemctl --no-pager status clinic-portal | head -5
fi

echo
echo "installed $ROLE"
echo "  break it:  sudo $ROOT/scripts/inject.sh"
echo "  heal it:   sudo $ROOT/scripts/revert.sh"
echo "  strip hints before evaluation: $ROOT/scripts/nuke.sh --target /opt/clinic"
