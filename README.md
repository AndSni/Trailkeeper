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
- **Offline-first project screen** - Room (`data/local/`) is a rebuildable
  cache of the synced entities. `SyncRepository` seeds a project once from
  `GET /sync/snapshot`, then every open runs the org-wide incremental loop
  `GET /sync/changes?since=<cursor>` (paged, deletes handled, cursor in
  `sync_state`). The detail screen renders straight from Room `Flow`s, so it
  shows the last sync offline and refreshes in place. Sign-out wipes the
  cache.
- **Write outbox** - creating a task / marking it done writes Room
  optimistically and queues an op in the `outbox` table. `drainOutbox()`
  (run before every pull, and right after an edit) posts the batch to
  `POST /sync/push`, folds the authoritative rows back in, and reports how
  many edits lost a last-writer-wins conflict.
- **Map tab** - MapLibre Native (`ui/map/`) in an `AndroidView`, trails as
  line layers and tasks as point layers fed from Room, camera auto-fits to
  the data, live-GPS puck via the location component. Base map is
  OpenFreeMap's free hosted "liberty" style; a self-hosted `.pmtiles` for
  true offline use is a later slice (BLUEPRINT §9).
- **Discussion tab + notifications** - the project's comment thread renders
  from Room (`MessageEntity`), posting goes through the outbox. A bell icon
  on the project list shows an unread badge and opens the notification inbox
  (`NotificationRepository` polls `GET /notifications`, mark-read syncs both
  ways). @mention picker is not built yet - mentions are backend-ready.

## What Phase 1 covers so far (geography core)

Needs **PostGIS** on the database (`CREATE EXTENSION postgis;` - Phase 0 runs
without it). Not yet built: MapLibre on Android, live GPS, offline tiles, GPX
*recording*, and the `POST /sync/push` write path (which co-evolves with the
Android Room outbox). This slice is the backend the field app pulls from.

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
- **Sync pull** - every mutation appends a `change_log` row (`app/sync.py`,
  an explicit call per route). `GET /sync/snapshot?project=<id>` returns a
  full bundle for first open; `GET /sync/changes?since=<server_seq>` streams
  everything after that cursor, collapsed to the latest state per entity,
  scoped to what the caller can see, with deletes as `op: "delete"`
- **Sync push** - `POST /sync/push` applies a batch of offline edits (task /
  work_log / message, upsert + delete), idempotent per `client_op_id`
  (`pushed_ops` table), whole-entity last-writer-wins via `base_updated_at`

## What Phase 2 covers (backend)

- **Discussion** - the project's own thread + one per task (`task_id` null vs
  set). `GET/POST /messages`, `DELETE /messages/{id}` (author or admin).
  Append-only, soft-deleted. Synced (snapshot, changes, and creatable via
  `/sync/push`)
- **@mentions** - `mention_user_ids` on a message, filtered to project
  members; a mention fires a higher-signal `mention` notification instead of
  the plain comment one
- **Notification inbox** - `notifications` table, `GET /notifications`
  `[?unread]` · `/unread-count` · `POST /notifications/read {ids|all}`.
  Types wired: `task_assigned` (on assignee add, incl. via push),
  `task_commented` / `project_commented`, `mention`. Never self-notify
- **FCM registration** - `device_tokens` + `POST /devices` (idempotent).
  Actual push dispatch is a stub in `app/notifications.py` until a Firebase
  project is set up for Trailkeeper

## Roadmap

`P1` map + offline tiles + live GPS + GPX import + tasks + sync ·
`P2` collaboration + notifications ·
`P3` route recording ·
`P4` segment timing ·
`P5` structures + inspections ·
`P6` insights + web console.
See [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) §15.
