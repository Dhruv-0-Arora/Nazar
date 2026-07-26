#!/usr/bin/env bash
# Install the brain-diagnostics skill into OpenClaw and brainctl onto PATH.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$BIN_DIR"
ln -sf "$HERE/brainctl" "$BIN_DIR/brainctl"
echo "linked $BIN_DIR/brainctl"

if [ -d "$(dirname "$SKILLS_DIR")" ]; then
  mkdir -p "$SKILLS_DIR/brain-diagnostics"
  ln -sf "$HERE/SKILL.md" "$SKILLS_DIR/brain-diagnostics/SKILL.md"
  echo "linked skill into $SKILLS_DIR/brain-diagnostics"
else
  echo "openclaw config dir not found; set OPENCLAW_SKILLS_DIR and re-run, or copy SKILL.md manually" >&2
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "note: add $BIN_DIR to PATH" ;;
esac
