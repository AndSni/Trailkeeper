# Trailkeeper

Self-hosted collaboration tool for trail-maintenance crews: an Android field
app plus a web console, backed by an API you run on your own server. A crew
shares a **project** workspace where several people record routes, log jobs,
time the work, talk it through, and get notified.

Modelled on [Trail Sentinel](https://trail-sentinel.com)'s feature set, with a
work-quantification model it doesn't have (measured segments → productivity
rates). Full plan: [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md).

> Status: **Phase 0** — identity + workspace core (backend + Android shell).

## Layout

| Path | What |
|------|------|
| `backend/` | FastAPI + SQLAlchemy 2.0 + Alembic API (Python 3.12+) |
| `android/` | Kotlin / Jetpack Compose field app — Gradle setup, theme and `ApiClient` probe reused from SharpRight (`com.asnidev.trailkeeper`) |
| `docs/` | Product & technical blueprint |

## Backend — quick start

Requires Python 3.12+, a PostgreSQL 14+ instance, and the `postgis` package
installed on it (`sudo dnf install postgis` / `sudo apt install
postgresql-<ver>-postgis-3` - Phase 0 didn't need this, Phase 1 does).

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# One-time: create the dev + test databases (adjust role/host to taste)...
createdb trailkeeper
createdb trailkeeper_test
# ...and enable PostGIS in each. CREATE EXTENSION needs a superuser, so this
# is the one step the app's own DB role can't do for itself:
sudo -u postgres psql -d trailkeeper -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d trailkeeper_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"

cp .env.example .env          # then edit DATABASE_URL + JWT_SECRET
alembic upgrade head
uvicorn app.main:app --reload --port 9110
```

API docs at <http://127.0.0.1:9110/docs>. Deployment: [`deploy/`](deploy/).

### Tests

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@127.0.0.1:5432/trailkeeper_test \
  python -m pytest
```

The suite creates the schema from the models, runs each test in a rolled-back
transaction, and skips itself entirely if no test database is reachable.

## Android — quick start

```bash
cd android
echo "sdk.dir=/path/to/Android/Sdk" > local.properties   # or let Android Studio write it
./gradlew :app:assembleDebug
```

The app resolves the backend three ways (external Cloudflare Tunnel → LAN →
`adb reverse tcp:9110 tcp:9110`), the same probe pattern as SharpRight's
`ApiClient`. Edit the `*_API_BASE_URL` fields in `app/build.gradle.kts` to
match your server.

## What Phase 0 covers

**Backend**

- Email + password auth with JWT access / refresh tokens
- Open registration that bootstraps the first organisation (owner)
- Invite links for every subsequent member
- Organisation settings, members, role changes (owner / admin / editor / viewer)
- Project CRUD with per-project membership and visibility rules
- Alembic migrations

**Android**

- Compose shell: login / create-organisation screen → project list with
  create-project dialog and sign-out
- `TokenStore` (DataStore) + an OkHttp `Authenticator` that refreshes the
  access token on a 401 and drops to the login screen if the refresh fails
- `Session` holds app-wide auth state; Gradle wrapper, theme scaffold and the
  backend-URL probe lifted from SharpRight

## What Phase 1 covers so far (geography core)

Needs **PostGIS** on the database (`CREATE EXTENSION postgis;` - Phase 0 runs
without it). Not yet built: MapLibre on Android, live GPS, offline tiles, the
`change_log` sync engine, GPX *recording*. This slice is the backend that
piece will talk to.

- **Trails** - org-wide `LineString` geometry, GPX import (`gpxpy`, one Trail
  per track segment), manual create via a point list, GeoJSON out, length
  computed on read (`ST_Length` on the geography cast, never stored)
- **Tasks** - `Point` geometry, priority/status, assignees, auto-attaches to
  the nearest trail within 75 m (`ST_Distance` on the geography cast) when
  created or moved, one-tap `/complete` that auto-logs a `WorkLog` from the
  task's estimate
- **Task photos** - uploaded to local disk (`backend/data/uploads/`, not
  MinIO - see `docs/BLUEPRINT.md` §16), served through an authenticated route
  that checks project visibility rather than a static file mount
- **Work logs** - hours against a task or a trail; editable by their author
  or an org admin
- Visibility for all of the above follows the same project-membership rules
  as Phase 0's projects (`app/authz.py`, shared by every route)

## Roadmap

`P1` map + offline tiles + live GPS + GPX import + tasks + sync ·
`P2` collaboration + notifications ·
`P3` route recording ·
`P4` segment timing ·
`P5` structures + inspections ·
`P6` insights + web console.
See [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) §15.
