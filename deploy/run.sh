#!/usr/bin/env bash
# Entry point for the systemd unit.
#
# Universal Auth machine identities do not give you a long-lived token. They
# give a client id and secret, which you exchange for an access token that
# expires (default 2h). A static token baked into the environment file works
# until the first reboot after it expires, and then the service fails to start
# with an auth error long after anyone touched anything.
#
# So we mint a fresh token here on every start, then hand it to `infisical run`.
set -euo pipefail

# Absolute paths: a systemd user unit does not get an interactive shell's PATH.
# `infisical` comes from nvm, so this is pinned to a Node version -- re-run
# `which infisical` after a Node upgrade. install.sh preflights both of these.
INFISICAL_BIN="$HOME/.nvm/versions/node/v24.14.1/bin/infisical"
UV_BIN="$HOME/.local/bin/uv"

: "${INFISICAL_CLIENT_ID:?not set - see the deploy section of README.md}"
: "${INFISICAL_CLIENT_SECRET:?not set - see the deploy section of README.md}"
: "${INFISICAL_PROJECT_ID:?not set - see the deploy section of README.md}"

token="$(
	"$INFISICAL_BIN" login \
		--method=universal-auth \
		--client-id="$INFISICAL_CLIENT_ID" \
		--client-secret="$INFISICAL_CLIENT_SECRET" \
		--plain --silent
)"

if [[ -z "$token" ]]; then
	echo "ERROR: Infisical login returned an empty token." >&2
	echo "       Check the client id/secret in ~/.config/drews-pokemon-app.env," >&2
	echo "       and that the identity still has access to the project." >&2
	exit 1
fi

exec "$INFISICAL_BIN" run \
	--projectId="$INFISICAL_PROJECT_ID" \
	--env=prod \
	--token="$token" \
	-- "$UV_BIN" run uvicorn api.app:app --host 127.0.0.1 --port 8000
