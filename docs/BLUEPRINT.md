# Trailkeeper — Product & Technical Blueprint

Draft v1 · 2026-09-04 · based on Trail Sentinel feature research and the
SharpRight stack.

A self-hosted collaboration tool for trail-maintenance crews: an Android field
app plus a web console, sharing a project workspace where several people record
routes, log jobs, time the work, comment, and get notified — with the data on
your own server.

---

## 0. Orientation

Trailkeeper is **project-based**. A project is a shared space — a trail
network, a work season, a build weekend — that several crew members open at
once. Inside it they see their live position on a map, record and import GPX
routes, drop markers for jobs and time how long each takes, record *segments*
of work with a quantity and a duration ("1.5 km brushcutting, 38 min"), leave
comments, get notified, and read a task list grouped by job type with total
work-time sums.

The closest existing product is **Trail Sentinel**; it covers most of this
already. We build our own for three reasons only:

1. **Data ownership** — it lives on your server.
2. **A work-quantification model Sentinel doesn't have** — measured segments →
   productivity rates.
3. **Reuse of the SharpRight stack** — FastAPI + SQLAlchemy + Alembic +
   Firebase, Kotlin/Compose Android — so the marginal build cost is low.

### Non-goals for v1

- No iOS client. The HTTP API stays client-agnostic so it's possible later,
  but it is not scoped.
- No public / anonymous trail-condition reporting (Trailforks / TrailsIQ
  territory). Trailkeeper is for a known crew.
- No multi-organisation SaaS. Single organisation, self-hosted — though every
  table carries `org_id` so this can change.
- No routing / navigation engine. Import and display routes, don't compute
  them.
- No billing, no marketing site.

---

## 1. Product principles

- **Your data.** Postgres + object store on your box. Every entity exportable
  as GeoJSON, GPX, CSV. No lock-in.
- **Offline is the default.** The field has no signal. The phone's local
  database is the source of truth for the UI; the network is a background
  reconciler.
- **Field-first UX.** One-handed, glove-friendly, big targets, readable in
  glare. The web console is where you read; the phone is where you do.
- **The project is the unit.** Membership, notifications, task lists, comments,
  exports — all scoped to a project.
- **Quantify the work.** Not just "3 hours on Blue Trail" but "1.5 km
  brushcut in 38 min with a 2-person crew" — so rates and estimates improve.
- **Reuse the rails.** SharpRight's FastAPI skeleton, config pattern, Alembic
  setup, Firebase dispatch, Android backend-probe and signing flow are lifted,
  not reinvented.

---

## 2. Parity with Trail Sentinel

Sourced from Trail Sentinel's feature, insights and release pages (Nov 2025).

| Capability | Trail Sentinel | Trailkeeper | Notes |
|---|---|---|---|
| Whole network on one map; filter by activity, difficulty, status | Yes | P1 | MapLibre; layer toggles |
| GPX import of existing trails | Yes | P1 | Parse to LineString, snap tasks to nearest trail |
| Export geo data for GIS | Yes | P3 | GeoJSON + GPX + CSV, server-side |
| Offline map; create tasks offline; auto-sync | Yes | P1 | Core of the build — §8 |
| Geolocated task: GPS on creation, photo, type, 4 priorities, auto-attach to trail | Yes | P1 | Priorities: low / medium / high / urgent |
| Task assignment, materials list, time estimate | Yes | P1–P2 | Assign to one or more members |
| Projects group tasks; real-time progress | Yes | P2 | Progress = closed / total, weighted by estimate |
| Conversation on task/project; @mentions; notify on reply | Yes | P2 | Sentinel shipped this in v1.6.0 |
| Notifications centre with history + read state | Yes | P2 | Needs a per-user inbox table (change from SharpRight's stateless topics) |
| Structure inventory; custom inspection forms; branded PDF; risk levels | Yes | P5 | Fixed JSON-schema forms first |
| Insights: hours/member, weekly trend, tasks closed, km maintained, structures inspected; filter by period/trail/type/member | Yes | P6 | Server-computed, cached |
| Exports: PDF, Excel, CSV, photo archive | Yes | P6 | WeasyPrint + openpyxl + zip |
| Role-based permissions | Yes | P0–P2 | Owner / Admin / Editor / Viewer + per-project membership |
| ~11 activity types, each with own trails/tasks/types | Yes | P0 | Configurable; MTB / hike / XC-ski / ATV / foot default |
| **Live GPS position** on the map | Not emphasised | **NEW · P1** | Continuous puck + accuracy ring |
| **GPX route recording** with quick job-marker buttons | — | **NEW · P3** | Foreground service; OSMTracker-style tap-to-mark |
| **Segment work records**: job type × measured length/area × timed duration → rate | — | **NEW · P4** | The reason to build. §10 |
| **Task list grouped by job type** with per-group time sums | Partial | **NEW · P2** | Group header shows Σ person-hours, Σ quantity, mean rate |

---

## 3. Domain model

Everything below `Organisation` carries `org_id`; most also carry
`project_id`, `created_by`, `created_at`, `updated_at`, `deleted_at`.

### Identity & access
- **Organisation** — the single tenant. Name, logo, default activity list, tz.
- **User** — email, name, password hash, avatar.
- **Membership** — User × Organisation × `org_role` (owner/admin/editor/viewer).
- **Invite** — email, token, role, inviting user, expiry, accepted-at.
- **Device** — per install: FCM token, platform, app version, last sync seq. *(P2)*

### Workspace
- **Project** — name, description, activity, status
  (planning/active/closed), area-of-interest polygon (optional, P1).
- **ProjectMember** — User × Project × `project_role` (lead/member).
- **Activity** — MTB, hiking, XC-ski, ATV, foot… configurable. *(seed in P0, admin UI later)*
- **JobType** — key, label, activity, `unit` (hours/km/m²/count), default crew,
  expected rate, colour, group. Drives grouped task lists and rollups. *(P4)*

### Geography *(P1+)*
- **Trail** — name, activity, difficulty, status, `geom` LineString (4326),
  source, length (generated).
- **TrailSegment** — a named sub-range of a trail.
- **Structure** — point asset: bridge, culvert, gate, sign, boardwalk.
- **Waypoint** — a quick marker dropped while recording; optional link to a Task.

### Work *(P1+)*
- **Task** — title, description, job type, priority, status, `geom` Point,
  nearest trail, assignees, time estimate, project.
- **TaskPhoto** — task, object-store key, sha256, caption, taken-at, EXIF point.
- **MaterialItem** — task, label, quantity, unit, obtained flag.
- **WorkLog** — hours against a task or a trail: member, minutes, date, note.
  Auto-created on task completion, editable retroactively.
- **GpxTrack** / **TrackPoint** — a recorded or imported route.
- **SegmentWorkRecord** — the measured-work entity. §10.

### Inspections *(P5)*
- **InspectionForm** — name, target structure type, JSON schema, version.
- **Inspection** — structure, form version, inspector, date, answers, risk, PDF.

### Collaboration & sync *(P2+)*
- **Thread** / **Message** / **Mention**.
- **Notification** — recipient, type, subject entity, actor, payload, read-at.
- **Attachment** — polymorphic file.
- **ChangeLog** — append-only: `server_seq`, entity, op, actor, `updated_at`.
  The spine of sync.

---

## 4. Database

PostgreSQL 16 (+ PostGIS 3 from P1). SQLAlchemy 2.0 models + Alembic, exactly
as SharpRight does it — add `GeoAlchemy2` for the `geometry` columns in P1.

Roles and statuses are stored as short strings guarded by CHECK constraints,
not native PG enums, to keep migrations painless. UUIDv7 primary keys
(time-ordered, `uuid.uuid7()` on Python 3.14; UUIDv4 fallback) so clients can
mint IDs offline.

Phase 0 tables: `organisations`, `users`, `memberships`, `invites`,
`projects`, `project_members`. See `backend/app/models.py`.

Phase 1 adds `trails`, `trail_segments`, `structures`, `waypoints`, `tasks`,
`task_assignees`, `task_photos`, `work_logs`, `gpx_tracks`, `track_points`,
and `change_log` — geometry columns are `geometry(<type>, 4326)`; lengths and
areas computed via `::geography`; GIST index on every `geom`, btree on
`(org_id, updated_at)`.

---

## 5. Architecture

A separate service on the same always-on box that runs SharpRight, behind the
same Cloudflare Tunnel, sharing nothing but the machine and the Postgres
instance.

```
Android field app  ──┐                        ┌── React + MapLibre GL JS (web console, P6)
(Kotlin/Compose/     │                        │
 MapLibre/Room)      ▼          HTTPS          ▼
              Cloudflare Tunnel → cutline… → Caddy (TLS, static console, .pmtiles range)
                                                │
                                                ▼
                          cutline-api.service — FastAPI + SQLAlchemy 2.0 + Alembic
                          (own venv, own .env, JWT auth)                NEW
                                                │
             ┌──────────────────────────────────┼───────────────────────────┐
             ▼                                  ▼                           ▼
   Postgres instance (shared host)      MinIO bucket `trailkeeper`   Firebase project (new)
   NEW database `trailkeeper` + PostGIS  photos, PDFs, .pmtiles       firebase_admin dispatch
   SharpRight's DB untouched
```

### Reused from SharpRight, near-verbatim
- FastAPI skeleton + `lifespan` + `/health`; `pydantic-settings` `config.py`;
  Alembic `env.py` layout.
- `firebase_admin` messaging dispatch — adapted from topic-only to per-user
  tokens.
- Android `ApiClient` three-way backend-URL probe (external tunnel / LAN /
  `adb reverse`); `keystore.properties` release signing; `deploy_android.sh`
  shape.
- APScheduler for periodic jobs (overdue-task sweep, digest, PDF cleanup).

### New, not in SharpRight
- **Real auth.** SharpRight uses one shared `API_KEY` header. Trailkeeper needs
  per-user JWT (access + refresh), password reset, invite acceptance.
- **PostGIS + GeoAlchemy2** and spatial queries (`ST_Length`, `ST_Area`,
  `ST_DWithin` for nearest-trail) — from P1.
- **Object store** (MinIO) with presigned upload/download.
- **The sync engine** (§8) — `change_log`, push endpoint, conflict handling.
- **Stateful notifications** — a per-user inbox with read state.
- **MapLibre** everywhere + a self-hosted vector-tile file.

---

## 6. Backend API

REST + JSON, FastAPI routers one per resource. Cursor pagination on lists
(`?updated_since=&cursor=`). From P1 all writes append to `change_log`
in-transaction.

| Group | Endpoints |
|---|---|
| `auth` | `POST /auth/register` · `/login` · `/refresh` · `/logout` · `POST /auth/invite/accept` · `GET /auth/me` |
| `org` | `GET/PATCH /org` · `GET /org/members` · `PATCH/DELETE /org/members/{user_id}` · `GET/POST /org/invites` · `DELETE /org/invites/{id}` |
| `projects` | `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` · `GET/POST /projects/{id}/members` · `DELETE /projects/{id}/members/{user_id}` |
| `trails` *(P1)* | `GET/POST/PATCH/DELETE /trails` · `POST /trails/import-gpx` · `GET /trails/{id}/segments` |
| `tasks` *(P1)* | `GET/POST/PATCH/DELETE /tasks` · `POST /tasks/{id}/photos` · `PATCH /tasks/{id}/assignees` · `POST /tasks/{id}/complete` |
| `work` *(P3)* | `GET/POST/PATCH/DELETE /work-logs` · `GET/POST/DELETE /gpx-tracks` · `GET /gpx-tracks/{id}/export.gpx` |
| `segments` *(P4)* | `GET/POST/PATCH/DELETE /segment-work` · `GET /segment-work/rollup?group_by=job_type\|trail\|member\|week` |
| `structures` *(P5)* | `GET/POST/PATCH/DELETE /structures` · `GET/POST /inspection-forms` · `GET/POST /inspections` · `GET /inspections/{id}/report.pdf` |
| `collab` *(P2)* | `GET/POST /threads/{id}/messages` · `GET /notifications?unread=1` · `POST /notifications/read` · `POST /devices` |
| `sync` *(P1)* | `GET /sync/changes?since={seq}` · `POST /sync/push` · `GET /sync/snapshot?project={id}` |
| `files` *(P1)* | `POST /uploads/sign` · `GET /files/{key}` |
| `insights` *(P6)* | `GET /insights/dashboard?project=&period=` · `GET /exports/{csv\|xlsx\|pdf\|photos}` |

**Sync push shape:** `POST /sync/push` takes a batch of `{entity_type,
entity_id, op, base_updated_at, fields, client_op_id}`. The server applies each
in one transaction, returns the authoritative row + the new `server_seq`, and
echoes `client_op_id` for idempotency.

---

## 7. Android app

Same stack family as SharpRight: Kotlin, Jetpack Compose, `minSdk 26` /
`targetSdk 36`, Firebase via `google-services`, release signing from
`keystore.properties`.

**Libraries** — MapLibre Native Android SDK (vector, offline `.pmtiles`, one
shared style JSON with the web console); Room (single source of truth for every
screen); a foreground `Service` for track recording (FusedLocationProvider,
~1 s cadence, `FOREGROUND_SERVICE_LOCATION`); WorkManager for sync push/pull
and photo upload with exponential backoff; Retrofit + OkHttp +
kotlinx-serialization; DataStore + `EncryptedSharedPreferences` for tokens.

**Modules** — `:core-auth`, `:core-sync`, `:core-map`, `:feature-projects`,
`:feature-tasks`, `:feature-recording`, `:feature-segments`,
`:feature-structures`, `:feature-collab`.

**Screens** — Project list · Project home (task list grouped by job type with
Σ time per group; conversation; jump to map) · Map (live puck + accuracy ring;
layers: trails / tasks / structures / my track; long-press → new task or
structure) · Record route (start/pause/stop; live distance, moving time,
elevation; big tap-to-mark buttons) · Task detail (photos, priority, job type,
assignees, materials, estimate, work logs, thread; one-tap "Mark done") ·
Segment work (§10) · Structure & inspection · Notifications · Offline maps.

**Manifest permissions** — `ACCESS_FINE_LOCATION`,
`ACCESS_BACKGROUND_LOCATION`, `FOREGROUND_SERVICE` +
`FOREGROUND_SERVICE_LOCATION`, `POST_NOTIFICATIONS`, `CAMERA`,
`ACCESS_NETWORK_STATE`.

---

## 8. Offline & sync

Kept deliberately narrow: few entity types, and in practice one editor per task
at a time.

**Write path** — UI writes to Room and enqueues an outbox row
`{entity_type, entity_id, op, fields, base_updated_at, client_op_id}`. A
WorkManager job drains the outbox to `POST /sync/push` in batches when
connectivity returns. The server applies each op in one transaction, stamps
`updated_at` / `updated_by`, appends to `change_log`, returns the authoritative
row + `server_seq`. Client overwrites its Room row and advances `last_seq`.

**Read path** — `GET /sync/changes?since={last_seq}&projects=…` streams every
`change_log` entry past the cursor. First open of a project pulls
`GET /sync/snapshot` then switches to the incremental cursor.

**Conflicts** — last-writer-wins per field-group. Push carries
`base_updated_at`; non-overlapping field-groups (status vs geometry vs
assignees) merge; a true overlap takes the server value and writes a row to a
**Sync conflicts** list the user can review. Deletes are tombstones
(`deleted_at`). Photos are content-addressed by sha256 and uploaded on their
own queue. Idempotency via `client_op_id`.

**Build vs buy** — hand-roll this narrow version (the `change_log` is ~1 table
+ 2 endpoints); keep the schema generic; revisit PowerSync / ElectricSQL only
if conflict handling gets painful in the field.

---

## 9. Maps & offline tiles

- **Renderer** — MapLibre: Native on Android, GL JS on the web console, one
  shared style JSON.
- **Tiles** — self-hosted, no tile-server process. Build a single `.pmtiles`
  for the Baltics from a Geofabrik extract with Planetiler; Caddy serves it
  with HTTP range requests.
- **Offline** — ship the home-region `.pmtiles` with the APK or as a first-run
  download; an "Offline maps" screen manages more regions.
- **Overlays** — trails (line by status), tasks (symbol by priority),
  structures (symbol by type), live track, position puck — all fed from Room.
- **Never** proxy `tile.openstreetmap.org` from the app (usage policy).

---

## 10. Segment-timing model

The capability nothing off-the-shelf offers, and the main reason to build.

**JobType** declares how its work is measured: `unit ∈ {hours, km, m², count}`,
a `default_crew`, and an optional `expected_rate` (e.g. brushcutting →
22 min/km, drainage dips → 6 min each). Job types are grouped (`sort_group`).

**SegmentWorkRecord** — one timed piece of work:

```
job_type      brushcutting (unit = km)
geom          LineString snapped along Blue Trail, 1.52 km
quantity      1.52   quantity_source = measured   (ST_Length on ::geography)
started_at    09:12      ended_at  10:04
pauses        [{09:33–09:41 fuel}]        active_seconds  2640
crew_size     2          equipment  ['brushcutter','rake']
notes         "heavy regrowth first 400 m"

derived, in queries / a SQL view — never stored:
  rate         = active_seconds / quantity        → 28.9 min/km
  throughput   = quantity / (active_seconds/3600) → 2.07 km/h
  person_hours = active_seconds/3600 * crew_size  → 1.47 p·h
  vs_expected  = rate − job_type.expected_rate    → +6.9 min/km
```

**Field flow** — on the map, snap-draw a line along the trail *or* tap "capture
from track" and let the live GPS trace define the geometry. Pick the job type;
Start; big Pause / Resume. Stop → the measured quantity is shown for
confirmation (editable → `quantity_source = manual`); set crew size and
equipment tags; save. Polygon jobs (unit = m²) draw an area; count jobs
(unit = count) tally with the timer running.

**Rollups** — `GET /segment-work/rollup?group_by=…` returns, per group (job
type / trail / member / ISO week): Σ quantity, Σ person-hours, mean rate, mean
vs expected. The project home's grouped task list uses the same aggregation:
*"Brushcutting — 14.2 km · 21.5 p·h · 26 min/km"*.

---

## 11. Insights & reporting

Matches Trail Sentinel's insights surface, computed server-side and cached. Web
console primarily; a read-only summary on the phone.

**Dashboard tiles** — hours per member for the period · weekly hours trend ·
tasks by status and by priority · km of trail maintained · structures inspected
+ risk mix · per-project progress % · **job-type productivity table**
(Trailkeeper-only: Σ quantity, Σ person-hours, mean rate, delta vs expected).

**Filters** — period (week / month / season / custom), project, trail, job
type, member.

**Exports** — CSV (raw rows) · XLSX (`openpyxl`, one sheet per entity) · PDF
(`WeasyPrint`, org logo + period header) · photo archive (zip + CSV manifest).
All server-side, streamed.

---

## 12. Notifications

SharpRight fires FCM to topics and keeps no per-user state. A collaboration app
needs a real inbox, so Trailkeeper adds a `notifications` table and
`device_tokens`, and keeps topic-style fan-out only for project-wide
broadcasts.

| Type | Trigger | Recipients |
|---|---|---|
| `task_assigned` | Added to a task's assignees | The assignee |
| `task_status_changed` | A task you're on or created moves state | Assignees + creator |
| `task_commented` | New message on a task thread | Thread participants |
| `mention` | `@name` in any message | The mentioned user |
| `project_invite` | Added to a project | The new member |
| `inspection_due` | Scheduler: structure past its interval | Project leads |
| `task_overdue` | Scheduler: open high/urgent task past estimate age | Assignees + leads |
| `sync_conflict` | Your offline edit lost a merge | The editor |

**Delivery** — write the `notifications` row, then push to the recipient's
registered `device_tokens` via the reused `firebase_admin` dispatch.
**In-app** — the Notifications screen reads the table: unread badge,
deep-links, per-project mute, "mark all read". A daily digest can come later
via APScheduler.

---

## 13. Roles & permissions

Two layers: an **org role** on the membership, and **per-project membership**
on top. A user can be an org Editor but only see the projects they're added to.

| Action | Owner | Admin | Editor | Viewer |
|---|:---:|:---:|:---:|:---:|
| Org settings, billing, delete org | ✓ | — | — | — |
| Invite / remove members, set roles | ✓ | ✓ | — | — |
| Manage activities, job types, inspection forms | ✓ | ✓ | — | — |
| Create project; add project members | ✓ | ✓ | lead only | — |
| Create / edit / close tasks, structures | ✓ | ✓ | in own projects | — |
| Log work, record tracks, segment work, inspections | ✓ | ✓ | in own projects | — |
| Comment / mention | ✓ | ✓ | in own projects | — |
| Import GPX trails, edit trail geometry | ✓ | ✓ | lead only | — |
| View project, run exports & insights | ✓ | ✓ | ✓ | view only |
| Hard-delete data | ✓ | own org | — | — |

*Phase 0 note:* project create/delete requires admin+ for now; the "Editor →
lead only" nuance lands with the project-creation UI.

---

## 14. Deployment

Same always-on machine as SharpRight (the old laptop behind the Cloudflare
Tunnel). Isolation by database, service, venv, bucket and subdomain — not by
hardware.

- **DNS** — `cutline.asnidev.com` for the API (name TBD — repo is Trailkeeper),
  `app.…` for the web console, both routed through the existing tunnel.
- **Database** — `CREATE DATABASE trailkeeper; CREATE EXTENSION postgis;` on
  the same Postgres instance. A dedicated role with rights on that DB only.
- **Service** — `trailkeeper-api.service` (systemd), own virtualenv, own
  `backend/.env`, Uvicorn workers behind Caddy. Never shares a process with
  SharpRight.
- **Object store** — MinIO as its own service if not already present; bucket
  `trailkeeper`, lifecycle rule to expire generated PDFs.
- **Push** — a new Firebase project (clean blast radius); its service-account
  JSON alongside SharpRight's, referenced by `firebase_credentials_path`.
- **Android** — new `applicationId` (e.g. `lv.asnidev.trailkeeper`), a new
  signing key backed up next to the SharpRight keystore, tester builds via
  Diawi.
- **Backups** — nightly `pg_dump trailkeeper` + `mc mirror` of the bucket,
  added to the existing backup cron.
- **Repo** — `git@github.com:AndSni/Trailkeeper.git`, standalone.

---

## 15. Roadmap

Each phase is shippable and testable with a real crew before the next starts.
Sizes are rough calendar effort for one developer working part-time.

| Phase | Focus | Ships | ~Size |
|---|---|---|---|
| **P0** | Foundations | Repo + CI; Postgres; Alembic; JWT auth + invites; Org / User / Membership; Project CRUD; Android shell + login + project list. | 2–3 wk |
| **P1** | Map & field core | MapLibre + offline `.pmtiles`; live GPS puck; GPX trail import; Task CRUD with photo / priority / job type / assignees; `change_log` + push/pull sync; photo upload queue. | 4–6 wk |
| **P2** | Collaboration | Project home; task list grouped by job type with time sums; threads + `@mentions`; notifications (inbox + FCM); role enforcement. | 3–4 wk |
| **P3** | Route recording | Foreground GPS service; pause/resume; tap-to-mark waypoint buttons; `GpxTrack` + points; GPX / GeoJSON export. | 2–3 wk |
| **P4** | Segment timing | Job-type admin; `SegmentWorkRecord` capture (snap-draw + from-track); pause-aware timer; productivity rollups; grouped views. | 3–4 wk |
| **P5** | Structures & inspections | Structure inventory; JSON-schema inspection forms; inspection capture with risk; branded PDF. | 3 wk |
| **P6** | Insights & web console | Cached dashboards; CSV / XLSX / PDF / photo-zip exports; React + MapLibre GL JS admin console. | 4–6 wk |
| **P7** | Harden | Sync-conflict UX; offline region manager polish; field beta with a crew; monitoring + backup verification. | ongoing |

**Minimum useful product** is the end of **P2**. P3–P4 are what make
Trailkeeper worth building over adopting Trail Sentinel.

---

## 16. Decisions to lock

| Decision | Resolution |
|---|---|
| Product name | **Trailkeeper** (repo created). |
| Multi-org vs single-org | Single-org for v1; `org_id` on every table so it's a later switch, not a rewrite. |
| Web console timing | Defer to P6. The field app is the product. |
| Object store | MinIO (presigned URLs, clean backup) — unless zero new services is preferred, then local disk behind Caddy with an `attachments` table. |
| Sync engine | Hand-roll the narrow `change_log` version. |
| Inspection forms | Fixed JSON-schema forms for P5. A visual builder only if a real need appears. |
| Firebase | New Firebase project, not a second app in SharpRight's. |
| Segment geometry | Allow both snap-to-trail and freehand; default to snapping. |
| Auth | Email + password + JWT (access/refresh), invite-link onboarding. No third-party IdP for v1. |
| API subdomain | TBD — `trailkeeper.asnidev.com` unless a shorter name is wanted. |

---

## 17. Open questions

1. Realistic crew size per project, and how often two people edit the *same*
   task offline at once? (Sets how much conflict UI is worth building.)
2. Do land managers need the branded **PDF** exports for v1, or is CSV/XLSX
   enough until P6?
3. Is **Latvia + Baltics** tile coverage sufficient to start?
4. Is there already a **MinIO** (or S3-compatible store) on the box?
5. Preferred Android `applicationId` namespace — `lv.asnidev.*`,
   `com.sharpright.*` sibling, or standalone?
6. Should **work logs** feed a payroll / volunteer-hours report format anyone
   specific expects (a grant body, a municipality)?
7. Any need for **equipment / asset tracking** beyond free-text tags on
   segment records (which brushcutter, service hours)?
