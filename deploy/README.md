# Deploying Trailkeeper

The API runs on the **same always-on server as SharpRight**
(`asnidev@192.168.50.27`), fully isolated: its own directory, venv, `.env`,
systemd service, port, database, and Cloudflare Tunnel hostname. Nothing is
shared except the machine and the PostgreSQL instance.

| Thing | Value |
|---|---|
| Server dir | `/home/asnidev/trailkeeper/backend` |
| Service | `trailkeeper-api.service` |
| Port | `8110` (localhost + LAN) |
| Public URL | `https://trailkeeper.asnidev.com` (Cloudflare Tunnel → `localhost:8110`) |
| Database | `trailkeeper` on the existing Postgres, role `trailkeeper` |

Port `8110` must match in three places: this service unit, the cloudflared
ingress, and the Android app's `LAN_API_BASE_URL` / `API_BASE_URL` in
`android/app/build.gradle.kts`.

---

## First-time server setup

Run these once, on the server.

### 1. Database

```bash
sudo -u postgres createuser --pwprompt trailkeeper
sudo -u postgres createdb --owner trailkeeper trailkeeper
# Phase 1 will also need:  sudo -u postgres psql -d trailkeeper -c 'CREATE EXTENSION postgis;'
```

### 2. Code + venv + .env

```bash
mkdir -p /home/asnidev/trailkeeper
# from your dev machine:
./scripts/deploy_backend.sh          # syncs code, makes the venv, runs migrations
                                     # (it will stop with "\.env missing" - that's next)

# back on the server:
cd /home/asnidev/trailkeeper/backend
cp /path/to/repo/deploy/env.production.example .env
$EDITOR .env                          # set DATABASE_URL password + JWT_SECRET
```

Then re-run `./scripts/deploy_backend.sh` from the dev machine; it will apply
migrations successfully this time.

### 3. systemd service

`deploy_backend.sh` only syncs `backend/`, so copy the unit over once from
the dev machine:

```bash
scp deploy/trailkeeper-api.service asnidev@192.168.50.27:/tmp/
```

then on the server:

```bash
sudo mv /tmp/trailkeeper-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trailkeeper-api.service
systemctl status trailkeeper-api.service
curl -s localhost:8110/health               # -> {"status":"ok"}
```

### 4. Cloudflare Tunnel

Add the public hostname (see `cloudflared-ingress.example.yml` for both the
dashboard and local-config forms):

- **Dashboard:** Zero Trust → Networks → Tunnels → your tunnel → Public
  Hostname → `trailkeeper` . `asnidev.com` → `HTTP` → `localhost:8110`.
- **Local config:** add the `ingress` rule, then
  `cloudflared tunnel route dns <tunnel> trailkeeper.asnidev.com` and restart
  the `cloudflared` service.

Verify from anywhere: `curl -s https://trailkeeper.asnidev.com/health`.

### 5. First account

While `ALLOW_REGISTRATION=true`, register once (from the app, or curl):

```bash
curl -sX POST https://trailkeeper.asnidev.com/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"you@example.com","name":"You","password":"a strong passphrase","organisation_name":"Your Crew"}'
```

Then set `ALLOW_REGISTRATION=false` in `.env` and
`sudo systemctl restart trailkeeper-api.service`. Everyone else joins by
invite (`POST /org/invites` → send them the token → `POST /auth/invite/accept`).

---

## Routine redeploy

From the dev machine, any time:

```bash
./scripts/deploy_backend.sh
```

It rsyncs `backend/` (never `.env`), updates the venv, runs
`alembic upgrade head`, and restarts the service. Override the target with
`TRAILKEEPER_REMOTE_HOST` / `TRAILKEEPER_REMOTE_DIR` env vars.

## Backups

Add to the server's existing backup cron, alongside SharpRight's:

```bash
pg_dump -Fc trailkeeper > "/backups/trailkeeper-$(date +%F).dump"
# from Phase 1, also mirror the object store / tiles directory
```

## Files here

| File | Purpose |
|---|---|
| `trailkeeper-api.service` | systemd unit for the API |
| `env.production.example` | template for the server's `backend/.env` |
| `cloudflared-ingress.example.yml` | the tunnel hostname rule |
| `Caddyfile.snippet` | **optional**, Phase 6 only — web console + `.pmtiles` serving |
