#!/usr/bin/env bash
# Container entry point.
#
# Universal Auth machine identities do not give you a long-lived token. They
# give a client id and secret, which you exchange for an access token that
# expires (default 2h). So we mint a fresh token on every container start,
# then hand it to `infisical run`, which injects OPENAI_API_KEY.
set -euo pipefail

: "${INFISICAL_CLIENT_ID:?not set - see the deploy section of README.md}"
: "${INFISICAL_CLIENT_SECRET:?not set - see the deploy section of README.md}"
: "${INFISICAL_PROJECT_ID:?not set - see the deploy section of README.md}"

token="$(
	infisical login \
		--method=universal-auth \
		--client-id="$INFISICAL_CLIENT_ID" \
		--client-secret="$INFISICAL_CLIENT_SECRET" \
		--plain --silent
)"

if [[ -z "$token" ]]; then
	echo "ERROR: Infisical login returned an empty token." >&2
	echo "       Check the client id/secret in the Dokploy environment settings," >&2
	echo "       and that the identity still has access to the project." >&2
	exit 1
fi

exec infisical run \
	--projectId="$INFISICAL_PROJECT_ID" \
	--env=prod \
	--token="$token" \
	-- "$@"
