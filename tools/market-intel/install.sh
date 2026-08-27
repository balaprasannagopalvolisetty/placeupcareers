#!/usr/bin/env bash
# PlaceUp market intelligence - Ubuntu installer. Idempotent; safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PLACEUP_REPO:-$HOME/PlaceUp}"

echo "==> installing to $HERE"
echo "==> PlaceUp repo expected at $REPO (override with PLACEUP_REPO=...)"

command -v python3 >/dev/null || { echo "python3 required: sudo apt install -y python3 python3-venv"; exit 1; }

[ -d "$HERE/.venv" ] || python3 -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install --quiet --upgrade pip
"$HERE/.venv/bin/pip" install --quiet pyyaml || echo "   (pyyaml unavailable - falling back to the built-in config reader)"

STATE_DIR="${INTEL_STATE:-$HOME/.local/state/placeup-intel}"
mkdir -p "$STATE_DIR" "$HERE/state"
export INTEL_STATE="$STATE_DIR"
echo "==> state dir: $STATE_DIR (must be a local filesystem - SQLite fails on mounted shares)"

if ! command -v claude >/dev/null; then
  cat <<'MSG'

  !! The Claude Code CLI is not on PATH. Install it once:

       curl -fsSL https://claude.ai/install.sh | bash

     then authenticate once, interactively:

       claude

     Authentication is the ONE step that needs a human. Everything after it runs unattended.

MSG
fi

echo "==> systemd user units"
mkdir -p "$HOME/.config/systemd/user"
sed "s|%h|$HOME|g" "$HERE/systemd/placeup-intel.service" > "$HOME/.config/systemd/user/placeup-intel.service"
cp "$HERE/systemd/placeup-intel.timer" "$HOME/.config/systemd/user/placeup-intel.timer"
systemctl --user daemon-reload
systemctl --user enable --now placeup-intel.timer

# Keep running when you are not logged in.
loginctl enable-linger "$USER" 2>/dev/null || echo "   (could not enable linger - runs only while logged in)"

echo
echo "==> verification"
"$HERE/.venv/bin/python" -m intel.run status || true
echo
systemctl --user list-timers placeup-intel.timer --no-pager || true
echo
echo "Done."
echo "  live log     : tail -f $STATE_DIR/intel.log"
echo "  force a pass : $HERE/.venv/bin/python -m intel.run watch"
echo "  health       : $HERE/.venv/bin/python -m intel.run status"
echo "  stop         : systemctl --user disable --now placeup-intel.timer"
