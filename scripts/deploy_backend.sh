#!/usr/bin/env bash
# Pushes backend/ to the always-on server over rsync/ssh, updates the venv,
# runs migrations, and restarts the API service. Safe to re-run any time -
# first deploy and every update after.
#
# .env is deliberately excluded: the server's .env holds production values
# (real DATABASE_URL / JWT_SECRET) that must never be overwritten by this
# machine's dev .env. Set it up once by hand (see deploy/env.production.example),
# then this script leaves it alone.
#
# Usage: ./scripts/deploy_backend.sh

set -euo pipefail

REMOTE_HOST="${TRAILKEEPER_REMOTE_HOST:-asnidev@192.168.50.27}"
REMOTE_DIR="${TRAILKEEPER_REMOTE_DIR:-/home/asnidev/trailkeeper/backend}"
SERVICE="trailkeeper-api.service"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

ok()   { echo "  [OK]   $1"; }
fail() { echo "  [FAIL] $1"; }

command -v rsync >/dev/null 2>&1 || { fail "rsync not found on PATH"; exit 1; }

echo "Syncing backend/ to $REMOTE_HOST:$REMOTE_DIR ..."
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"
rsync -az --delete \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '**/__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.ruff_cache/' \
    --exclude '*.log' \
    --exclude '.env' \
    "$BACKEND_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"
ok "Files synced"

echo "Updating venv and applying migrations on the server..."
ssh "$REMOTE_HOST" bash -s <<REMOTE_SCRIPT
    set -euo pipefail
    cd "$REMOTE_DIR"
    [ -d venv ] || python3 -m venv venv
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    [ -f .env ] || { echo "  [FAIL] $REMOTE_DIR/.env missing - see deploy/env.production.example"; exit 1; }
    alembic upgrade head
REMOTE_SCRIPT
ok "Dependencies installed, migrations applied"

echo "Restarting $SERVICE ..."
if ssh "$REMOTE_HOST" "systemctl list-unit-files | grep -q '$SERVICE'"; then
    ssh "$REMOTE_HOST" "sudo systemctl restart $SERVICE"
    ssh "$REMOTE_HOST" "systemctl is-active $SERVICE" && ok "$SERVICE restarted"
else
    fail "$SERVICE not installed yet - see deploy/README.md (expected before first-time setup is done)"
fi

echo ""
echo "Done."
