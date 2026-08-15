#!/usr/bin/env bash
# Build the frontend, install the user service, and publish it on the tailnet.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="drews-pokemon-app.service"

echo "Building the frontend..."
(cd "$REPO_ROOT/web" && npm ci && npm run build)

echo "Installing the user service..."
mkdir -p "$UNIT_DIR"
cp "$REPO_ROOT/deploy/$UNIT_NAME" "$UNIT_DIR/$UNIT_NAME"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

echo "Allowing the service to run without an active login..."
loginctl enable-linger "$USER"

echo "Publishing on the tailnet over HTTPS..."
sudo tailscale serve --bg 8000

echo
systemctl --user --no-pager status "$UNIT_NAME" | head -12
echo
tailscale serve status
