# Deploy status

Parked 2026-11-18. The container is built and tested locally. It is not deployed.
About 15 minutes of work in Infisical and Dokploy remains.

## Done

- `Dockerfile`, `.dockerignore`, `deploy/entrypoint.sh` on `main` at `1218936`.
- The old systemd deploy is removed. It was never installed.
- Image built on the Minisforum and run against the real data with a dummy key
  and the Infisical entrypoint bypassed. Health, frontend, deep-link fallback,
  artwork and `/api/conversations` all answered. It runs as uid 1000 and can
  write `app.db`. With no credentials the entrypoint refuses to start.
- Data copied to `/srv/apps/drew-pokemon/data` (193 MB, includes Drew's
  `app.db`). The copy in this repo's `data/` is untouched. If the app is used
  from the repo folder before the deploy, copy `app.db` across again.

## Not done, in order

1. Create the Infisical machine identity. See "Creating the Infisical machine
   identity" in the README. It did not exist on 2026-11-18.
2. In Dokploy (`https://pop-os.tail1f6182.ts.net:8443`), delete the
   `hello-world` app. It owns the bare hostname.
3. Create the app with the values in the README's "Dokploy settings" table and
   the three `INFISICAL_*` environment variables.
4. Deploy.

## Verify after deploy

- The Dokploy build log ends in success. This is the first build from GitHub on
  this box, so it is also the proof for the platform.
- Container logs show uvicorn started, with no Infisical auth error.
- `https://pop-os.tail1f6182.ts.net/api/health` returns `status: ok`.
- One real question answers and `spent_today_usd` moves off zero.
- Drew's old conversations show in the sidebar.
- `docker ps` still shows `dokploy-traefik` on `127.0.0.1:8080->80/tcp`.

## Never tested

- `infisical login` and `infisical run` inside the container.
- A real chat turn from the container.
- Deploy on push. GitHub webhooks cannot reach a tailnet-only box, so deploys
  are a manual click in Dokploy until the webhook path is exposed.

## Known rough edges

- The image is 592 MB. The Infisical CLI binary is 162 MB of that.
- Nothing has been seen in a browser yet. See `KNOWN-ISSUES.md`.

Platform context lives in `~/Developer/minisforum-platform/PLAN.md`, step 3.
