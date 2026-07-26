#!/usr/bin/env bash
# install.sh - deploy the scenario onto a laptop. REQUIRES sudo/root.
#
# Usage:
#   sudo ./install.sh laptop-a                          # backend + mock-db + its corpus docs
#   sudo ./install.sh laptop-b http://<laptop-a-ip>:3001  # frontend + its corpus docs
#
# What it does:
#   - copies code to /opt/myapp/
#   - writes env files to /etc/myapp/ (backend log goes to /var/log/myapp/)
#   - installs and enables systemd units from this directory
#   - copies this machine's corpus docs (per corpus/placement.json) to /opt/company-docs/
#   - never copies ground_truth.md or placement.json to the machine's corpus
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run with sudo (installs to /opt, /etc, /var/log, systemd)." >&2
  exit 1
fi

ROLE="${1:-}"
BACKEND_URL="${2:-}"
if [[ "$ROLE" != "laptop-a" && "$ROLE" != "laptop-b" ]]; then
  echo "usage: sudo $0 laptop-a | laptop-b [backend-url]" >&2
  exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="$(dirname "$DEPLOY_DIR")"

install_corpus() {
  local role="$1"
  mkdir -p /opt/company-docs
  local docs
  docs="$(node -e "
    const p = require('${SCENARIO_DIR}/corpus/placement.json');
    console.log((p['${role}'] || []).join('\n'));
  ")"
  while IFS= read -r doc; do
    [[ -n "$doc" ]] || continue
    install -m 0644 "${SCENARIO_DIR}/corpus/${doc}" "/opt/company-docs/${doc}"
  done <<< "$docs"
  echo "corpus for ${role} installed to /opt/company-docs/:"
  ls /opt/company-docs/
}

mkdir -p /etc/myapp /var/log/myapp

if [[ "$ROLE" == "laptop-a" ]]; then
  mkdir -p /opt/myapp/backend /opt/myapp/mock-db
  install -m 0644 "${SCENARIO_DIR}/backend/server.js" /opt/myapp/backend/server.js
  install -m 0644 "${SCENARIO_DIR}/mock-db/server.js" /opt/myapp/mock-db/server.js
  # System env file: same healthy defaults, but log to /var/log/myapp.
  sed 's|^LOG_FILE=.*|LOG_FILE=/var/log/myapp/backend.log|' \
    "${SCENARIO_DIR}/backend/backend.env" > /etc/myapp/backend.env
  install -m 0644 "${DEPLOY_DIR}/backend.service" /etc/systemd/system/backend.service
  install -m 0644 "${DEPLOY_DIR}/mock-db.service" /etc/systemd/system/mock-db.service
  systemctl daemon-reload
  systemctl enable --now mock-db backend
  install_corpus laptop-a
  echo "laptop-a installed: mock-db (5432) + backend (3001), env at /etc/myapp/backend.env."
else
  mkdir -p /opt/myapp/frontend
  install -m 0644 "${SCENARIO_DIR}/frontend/server.js" /opt/myapp/frontend/server.js
  install -m 0644 "${SCENARIO_DIR}/frontend/index.html" /opt/myapp/frontend/index.html
  {
    echo "PORT=8080"
    echo "BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:3001}"
    echo "LOG_FILE=/var/log/myapp/frontend.log"
  } > /etc/myapp/frontend.env
  if [[ -z "$BACKEND_URL" ]]; then
    echo "WARNING: no backend URL given; edit BACKEND_URL in /etc/myapp/frontend.env to point at laptop A." >&2
  fi
  install -m 0644 "${DEPLOY_DIR}/frontend.service" /etc/systemd/system/frontend.service
  systemctl daemon-reload
  systemctl enable --now frontend
  install_corpus laptop-b
  echo "laptop-b installed: frontend (8080), env at /etc/myapp/frontend.env."
fi
