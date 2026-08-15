#!/usr/bin/env bash
# Build the frontend, install the user service, and publish it on the tailnet.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="drews-pokemon-app.service"
UNIT_FILE="$REPO_ROOT/deploy/$UNIT_NAME"

# --- Preflight: every binary deploy/run.sh references must exist at the path
# it names, and must match what's actually installed right now.
# `infisical`'s path is pinned to a specific nvm/Node version, so a Node
# upgrade silently breaks the unit; catching that here, before anything is
# installed, beats a service that fails at boot with a confusing error.
echo "Checking the launcher's binary paths..."

RUN_SCRIPT="$REPO_ROOT/deploy/run.sh"
if [[ ! -x "$RUN_SCRIPT" ]]; then
	echo "ERROR: $RUN_SCRIPT is missing or not executable." >&2
	exit 1
fi

infisical_unit_path="$(grep -oE 'INFISICAL_BIN="[^"]+"' "$RUN_SCRIPT" | head -1 | sed 's|.*="||; s|"$||; s|\$HOME|'"$HOME"'|')"
uv_unit_path="$(grep -oE 'UV_BIN="[^"]+"' "$RUN_SCRIPT" | head -1 | sed 's|.*="||; s|"$||; s|\$HOME|'"$HOME"'|')"

# The unit's EnvironmentFile has no leading '-', so systemd refuses to even start
# without it -- and ${INFISICAL_PROJECT_ID} in ExecStart comes from it. Catching a
# missing file here beats a service that fails at boot with no obvious cause.
env_file="$HOME/.config/drews-pokemon-app.env"
if [[ ! -f "$env_file" ]]; then
	echo "ERROR: $env_file does not exist." >&2
	echo "       The service will refuse to start without it. See the README's" >&2
	echo "       deploy section for what it must contain, then re-run this script." >&2
	exit 1
fi

for var in INFISICAL_CLIENT_ID INFISICAL_CLIENT_SECRET INFISICAL_PROJECT_ID; do
	if ! grep -q "^${var}=" "$env_file"; then
		echo "ERROR: $env_file is missing ${var}." >&2
		echo "       Universal Auth needs a client id and secret, not a static token." >&2
		echo "       See the deploy section of README.md." >&2
		exit 1
	fi
done

if grep -q "^INFISICAL_TOKEN=" "$env_file"; then
	echo "WARNING: $env_file still sets INFISICAL_TOKEN. That is no longer used;" >&2
	echo "         the token is minted at each start by deploy/run.sh. Safe to remove." >&2
fi

if [[ -z "$infisical_unit_path" || -z "$uv_unit_path" ]]; then
	echo "ERROR: could not find both INFISICAL_BIN and UV_BIN in $RUN_SCRIPT." >&2
	echo "       Check those assignments haven't drifted from the expected format." >&2
	exit 1
fi

for bin_path in "$infisical_unit_path" "$uv_unit_path"; do
	if [[ ! -x "$bin_path" ]]; then
		echo "ERROR: run.sh references '$bin_path', which does not exist or is not executable." >&2
		echo "       Run 'which infisical uv' and fix the paths in $RUN_SCRIPT, then re-run this script." >&2
		exit 1
	fi
done

# The unit is version-pinned by design (systemd needs an absolute path), but
# it should still match reality right now -- if PATH resolves a different
# binary than the one the unit names, installing anyway would silently run
# a stale binary at boot.
actual_infisical="$(command -v infisical || true)"
actual_uv="$(command -v uv || true)"

if [[ -n "$actual_infisical" && "$actual_infisical" != "$infisical_unit_path" ]]; then
	echo "ERROR: 'which infisical' resolves to '$actual_infisical'," >&2
	echo "       but $UNIT_NAME's ExecStart references '$infisical_unit_path'." >&2
	echo "       Update ExecStart in $UNIT_FILE to match, then re-run this script." >&2
	exit 1
fi

if [[ -n "$actual_uv" && "$actual_uv" != "$uv_unit_path" ]]; then
	echo "ERROR: 'which uv' resolves to '$actual_uv'," >&2
	echo "       but $UNIT_NAME's ExecStart references '$uv_unit_path'." >&2
	echo "       Update ExecStart in $UNIT_FILE to match, then re-run this script." >&2
	exit 1
fi

echo "  infisical: $infisical_unit_path (matches PATH)"
echo "  uv:        $uv_unit_path (matches PATH)"

echo "Building the frontend..."
(cd "$REPO_ROOT/web" && npm ci && npm run build)

echo "Installing the user service..."
mkdir -p "$UNIT_DIR"
cp "$UNIT_FILE" "$UNIT_DIR/$UNIT_NAME"
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
