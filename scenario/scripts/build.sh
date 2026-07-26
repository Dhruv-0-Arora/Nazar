#!/usr/bin/env bash
# Builds the deployable artifact.
#
# Produces dist/ — minified CommonJS bundles plus static assets. That directory
# is what ships to a clinic host and what systemd runs. No source, no
# node_modules, no package.json on the target: the bundles have zero runtime
# dependencies and execute on a stock `node`.
#
# esbuild is a BUILD-time dependency and stays on the build host. The rule that
# nothing may need `npm install` applies to the deployed machine, which cannot
# reach a registry — not to the machine doing the building.
#
#   scripts/build.sh          build
#   scripts/build.sh --clean  wipe dist/ first

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"

[ "${1:-}" = "--clean" ] && { rm -rf "$DIST"; echo "cleaned dist/"; }
mkdir -p "$DIST/public"

bundle() {
  local entry="$1" out="$2"
  npx --no-install esbuild "$ROOT/$entry" \
    --bundle \
    --platform=node \
    --target=node20 \
    --format=cjs \
    --minify \
    --legal-comments=none \
    --outfile="$DIST/$out" \
    --log-level=warning
  printf '  %-14s <- %s\n' "$out" "$entry"
}

echo "building…"
bundle backend/server.js  backend.js
bundle frontend/server.js portal.js
bundle mockdb/server.js   mockdb.js

# Browser assets get minified too. Shipping readable client source next to
# minified server bundles is the tell that the artifact was assembled by hand.
npx --no-install esbuild "$ROOT/frontend/public/app.js" \
  --bundle --minify --target=es2020 --legal-comments=none \
  --outfile="$DIST/public/app.js" --log-level=warning
npx --no-install esbuild "$ROOT/frontend/public/styles.css" \
  --minify --legal-comments=none \
  --outfile="$DIST/public/styles.css" --log-level=warning
cp "$ROOT/frontend/public/index.html" "$DIST/public/index.html"

cp "$ROOT/mockdb/patients.json" "$DIST/patients.json"
echo "  public/app.js    <- minified"
echo "  public/styles.css<- minified"
echo "  public/index.html"
echo "  patients.json <- mockdb/patients.json"

# Version stamp, the sort of thing a real build leaves behind. Carries no
# reference to how the artifact was produced beyond the version.
cat > "$DIST/BUILD" <<EOF
service=clinic-services
version=$(node -p "require('$ROOT/package.json').version")
node=$(node --version)
EOF
echo "  BUILD"

echo
echo "artifact: $DIST"
du -sh "$DIST" | awk '{print "size:     " $1}'
echo
echo "run it:"
echo "  node dist/mockdb.js"
echo "  node dist/backend.js"
echo "  node dist/portal.js"
