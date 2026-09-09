"""SQLAlchemy models for Trailkeeper Phase 0.

Phase 0 is the identity + workspace core: organisations, users, memberships,
invites, projects and project members. Geography (trails, tasks, tracks,
structures) and the sync change-log arrive in Phase 1 - see docs/BLUEPRINT.md.

Roles and statuses are stored as short strings guarded by CHECK constraints
rather than native PG enums, which keeps migrations painless. The allowed
values are mirrored by the string enums below, used for validation in the
Pydantic schemas.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> uuid.UUID:
    """Time-ordered UUIDv7 where available (Python 3.14+), else UUIDv4.

    Clients mint IDs offline before the server ever sees the row, so the app
    generates them rather than leaning on a DB sequence.
    """
    gen = getattr(uuid, "uuid7", uuid.uuid4)
    return gen()


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrgRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class ProjectRole(enum.StrEnum):
    lead = "lead"
    member = "member"


class ProjectStatus(enum.StrEnum):
    planning = "planning"
    active = "active"
    closed = "closed"


class TrailStatus(enum.StrEnum):
    open = "open"
    closed = "closed"
    needs_work = "needs_work"


class TaskPriority(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TaskStatus(enum.StrEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    wontfix = "wontfix"


class StructureType(enum.StrEnum):
    culvert = "culvert"
    bridge = "bridge"
    boardwalk = "boardwalk"
    ford = "ford"
    steps = "steps"
    retaining_wall = "retaining_wall"
    drain = "drain"
    waterbar = "waterbar"
    sign = "sign"
    gate = "gate"
    bench = "bench"
    kiosk = "kiosk"
    other = "other"


class StructureStatus(enum.StrEnum):
    good = "good"
    monitor = "monitor"
    needs_repair = "needs_repair"
    failed = "failed"
    decommissioned = "decommissioned"


class InspectionRisk(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TrackSource(enum.StrEnum):
    recorded = "recorded"  # captured live by the field app
    imported = "imported"  # uploaded from a GPX file


_ORG_ROLES = ", ".join(f"'{r.value}'" for r in OrgRole)
_PROJECT_ROLES = ", ".join(f"'{r.value}'" for r in ProjectRole)
_PROJECT_STATUSES = ", ".join(f"'{s.value}'" for s in ProjectStatus)
_TRAIL_STATUSES = ", ".join(f"'{s.value}'" for s in TrailStatus)
_TASK_PRIORITIES = ", ".join(f"'{p.value}'" for p in TaskPriority)
_TASK_STATUSES = ", ".join(f"'{s.value}'" for s in TaskStatus)
_STRUCTURE_TYPES = ", ".join(f"'{t.value}'" for t in StructureType)
_STRUCTURE_STATUSES = ", ".join(f"'{s.value}'" for s in StructureStatus)
_INSPECTION_RISKS = ", ".join(f"'{r.value}'" for r in InspectionRisk)
_TRACK_SOURCES = ", ".join(f"'{s.value}'" for s in TrackSource)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Organisation(Base, TimestampMixin):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id", name="uq_membership_org_user"),
        CheckConstraint(f"org_role in ({_ORG_ROLES})", name="ck_membership_org_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_role: Mapped[str] = mapped_column(String(16), default=OrgRole.editor.value, nullable=False)

    organisation: Mapped[Organisation] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(f"org_role in ({_ORG_ROLES})", name="ck_invite_org_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    org_role: Mapped[str] = mapped_column(String(16), default=OrgRole.editor.value, nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organisation: Mapped[Organisation] = relationship()


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(f"status in ({_PROJECT_STATUSES})", name="ck_project_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    activity: Mapped[str] = mapped_column(String(64), default="mtb", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ProjectStatus.planning.value, nullable=False
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organisation: Mapped[Organisation] = relationship(back_populates="projects")
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
        CheckConstraint(f"project_role in ({_PROJECT_ROLES})", name="ck_project_member_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_role: Mapped[str] = mapped_column(
        String(16), default=ProjectRole.member.value, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


# --------------------------------------------------------------------------- #
# Geography & work (Phase 1) - see docs/BLUEPRINT.md sec 3-4.
#
# Trails are org-wide (the whole network on one map, per Trail Sentinel),
# not scoped to a project. Geometry columns keep GeoAlchemy2's default
# spatial_index=True and alembic/env.py wires in geoalchemy2's render_item /
# include_object helpers, so autogenerate creates and tracks the GIST index
# correctly instead of flagging it as drift on every future migration.
# --------------------------------------------------------------------------- #


class Trail(Base, TimestampMixin):
    __tablename__ = "trails"
    __table_args__ = (CheckConstraint(f"status in ({_TRAIL_STATUSES})", name="ck_trail_status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    activity: Mapped[str] = mapped_column(String(64), default="mtb", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=TrailStatus.open.value, nullable=False)
    geom: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=False
    )
    # "imported" (GPX) or "drawn" (traced on the map) - purely informational.
    source: Mapped[str] = mapped_column(String(16), default="imported", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"priority in ({_TASK_PRIORITIES})", name="ck_task_priority"),
        CheckConstraint(f"status in ({_TASK_STATUSES})", name="ck_task_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Free text until Phase 4 introduces the JobType taxonomy table, which
    # this will migrate onto (see docs/BLUEPRINT.md sec 10, sec 16).
    task_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), default=TaskPriority.medium.value, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.open.value, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    nearest_trail_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trails.id", ondelete="SET NULL"), nullable=True
    )
    estimate_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship()
    photos: Mapped[list[TaskPhoto]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskAssignee(Base):
    __tablename__ = "task_assignees"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class TaskPhoto(Base, TimestampMixin):
    __tablename__ = "task_photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Relative to settings.upload_dir - never a client-controlled path (the
    # route generates it, see routes/tasks.py:_save_photo_file).
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    task: Mapped[Task] = relationship(back_populates="photos")


class WorkLog(Base, TimestampMixin):
    __tablename__ = "work_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    trail_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trails.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    worked_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    # True for the log a task's "Mark done" auto-creates from its estimate -
    # distinguishes it from hours entered by hand (see docs/BLUEPRINT.md sec 3).
    auto_from_task: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# --------------------------------------------------------------------------- #
# Sync spine (Phase 1b) - see docs/BLUEPRINT.md sec 8.
#
# Every mutating route calls app.sync.record_change(), which appends one row
# here in the same transaction. Offline clients pull `GET /sync/changes?since=
# <server_seq>` to catch up. `entity_id` / `project_id` carry no FK on
# purpose: a change row must outlive the row it describes so a delete still
# propagates.
# --------------------------------------------------------------------------- #

CHANGE_ENTITY_TYPES = (
    "project",
    "project_member",
    "trail",
    "task",
    "work_log",
    "message",
    "job_type",
    "segment_work",
    "structure",
    "inspection_form",
    "inspection",
    "track",
)


class ChangeLog(Base):
    __tablename__ = "change_log"
    __table_args__ = (
        CheckConstraint("op in ('upsert', 'delete')", name="ck_change_log_op"),
        Index("ix_change_log_org_seq", "organisation_id", "server_seq"),
    )

    server_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    op: Mapped[str] = mapped_column(String(8), nullable=False)
    # Null for org-wide entities (trails); set for project-scoped ones so a
    # client only syncing certain projects can filter the stream.
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class PushedOp(Base):
    """Idempotency ledger for `POST /sync/push`. A retried batch (flaky
    network, app restart mid-push) re-sends the same client-generated
    `client_op_id`s; if one is already here, the op is not re-applied - the
    stored outcome + the entity's current state are returned instead.
    """

    __tablename__ = "pushed_ops"

    client_op_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # applied|conflict|rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
# Collaboration (Phase 2) - comment threads, @mentions, the notification inbox.
# See docs/BLUEPRINT.md sec 12.
#
# A "thread" is just the set of messages sharing a subject: task_id set = that
# task's thread, task_id null = the project's thread. Messages are append-only
# (soft-deleted, never edited) so they need no updated_at and sync through
# /sync/push as create-or-delete.
# --------------------------------------------------------------------------- #


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread", "project_id", "task_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # User ids the client flagged as @mentioned (resolved from the member list
    # on the client). Stored as JSON - never queried by element.
    mentioned_user_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient", "recipient_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # task_assigned | task_status_changed | task_commented | project_commented | mention
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # subject_type: task | project | message
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(String(500), nullable=False)  # pre-rendered summary
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceToken(Base):
    """FCM registration tokens per install - the push side of notifications.
    Populated now; actual `firebase_admin` dispatch is wired when a Firebase
    project exists (see app/notifications.py)."""

    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    fcm_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), default="android", nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
# Segment timing (Phase 4) - the feature nothing off-the-shelf offers.
# See docs/BLUEPRINT.md sec 10.
#
# A JobType defines how a kind of work is measured (its `unit`) and, optionally,
# an `expected_rate` in minutes-per-unit to compare against. A
# SegmentWorkRecord is one timed piece of that work: a geometry (line / area /
# point), a measured or hand-entered quantity, and the active (un-paused)
# seconds it took. Rates, throughput and person-hours are DERIVED in queries,
# never stored.
# --------------------------------------------------------------------------- #

JOB_UNITS = ("hours", "km", "m2", "count")
_JOB_UNITS_SQL = ", ".join(f"'{u}'" for u in JOB_UNITS)

# key, label, unit, default_crew, expected_rate (min per unit or None), colour, group
DEFAULT_JOB_TYPES = (
    ("brushcutting", "Brushcutting", "km", 2, 22.0, "#4C6B3C", "Vegetation"),
    ("hand_clearing", "Hand clearing", "km", 2, 40.0, "#4C6B3C", "Vegetation"),
    ("tread_repair", "Tread repair", "m2", 2, None, "#8A6A4A", "Tread"),
    ("blowdown_clearing", "Blowdown clearing", "count", 2, 12.0, "#8A6A4A", "Tread"),
    ("drainage_dip", "Drainage dip", "count", 1, 6.0, "#2F5A6B", "Drainage"),
    ("waterbar", "Waterbar", "count", 2, 25.0, "#2F5A6B", "Drainage"),
    ("signage", "Signage", "count", 1, None, "#B7791F", "Furniture"),
    ("general", "General trail work", "hours", 1, None, "#5C6450", "Other"),
)


class JobType(Base, TimestampMixin):
    __tablename__ = "job_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "activity", "key", name="uq_job_type_key"),
        CheckConstraint(f"unit in ({_JOB_UNITS_SQL})", name="ck_job_type_unit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    activity: Mapped[str] = mapped_column(String(64), default="mtb", nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    default_crew: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Target minutes per unit (min/km, min each, ...). Null = no target set.
    expected_rate: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    sort_group: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SegmentWorkRecord(Base, TimestampMixin):
    __tablename__ = "segment_work_records"
    __table_args__ = (
        CheckConstraint(
            "quantity_source in ('measured', 'manual')", name="ck_swr_quantity_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_types.id", ondelete="SET NULL"), nullable=True
    )
    trail_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trails.id", ondelete="SET NULL"), nullable=True
    )
    # LineString | Polygon | Point, 4326. Optional (a count job may have none).
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity_source: Mapped[str] = mapped_column(String(8), default="manual", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Wall time minus pauses - the number rates are computed against.
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pauses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    crew_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    equipment: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------- #
# Structures & inspections (Phase 5) - see docs/BLUEPRINT.md sec 3, sec 15.
#
# A Structure is a built asset on the network (culvert, bridge, sign, ...) -
# org-wide like a Trail, with a Point location that auto-attaches to the
# nearest trail. An InspectionForm is a reusable JSON-schema questionnaire
# (org-wide, versioned); an Inspection is one filled-in form against one
# structure, recorded in a project's context. An inspection may carry a
# `condition` that writes back to the structure's status.
# --------------------------------------------------------------------------- #

INSPECTION_FIELD_TYPES = ("bool", "text", "number", "choice", "section")


class Structure(Base, TimestampMixin):
    __tablename__ = "structures"
    __table_args__ = (
        CheckConstraint(f"structure_type in ({_STRUCTURE_TYPES})", name="ck_structure_type"),
        CheckConstraint(f"status in ({_STRUCTURE_STATUSES})", name="ck_structure_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    structure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=StructureStatus.good.value, nullable=False
    )
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    nearest_trail_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trails.id", ondelete="SET NULL"), nullable=True
    )
    material: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # Map marker colour, "#rrggbb" or "" for the client default.
    color: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    installed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # For the future `inspection_due` scheduler (BLUEPRINT sec 12); null = no
    # routine interval.
    inspection_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InspectionForm(Base, TimestampMixin):
    __tablename__ = "inspection_forms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Which StructureType this form is meant for; "" = any structure.
    target_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # List of field defs: {key, label, type, required?, choices?, help?}.
    # `type` is one of INSPECTION_FIELD_TYPES. Not queried by element.
    schema_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Bumped on every edit so an Inspection can pin the version it answered.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Inspection(Base, TimestampMixin):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint(
            f"risk is null or risk in ({_INSPECTION_RISKS})", name="ck_inspection_risk"
        ),
        CheckConstraint(
            f"condition is null or condition in ({_STRUCTURE_STATUSES})",
            name="ck_inspection_condition",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    structure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("structures.id", ondelete="CASCADE"), index=True, nullable=False
    )
    form_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inspection_forms.id", ondelete="SET NULL"), nullable=True
    )
    form_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    inspected_on: Mapped[date] = mapped_column(Date, nullable=False)
    # Answers keyed by the form field `key`. Free-form when there's no form.
    answers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # If set, writes back to the structure's status on save.
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Branded PDF export lands in P6 (BLUEPRINT sec 11); column reserved.
    pdf_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------- #
# GPX tracks (Phase 3) - a route recorded live by the field app or uploaded
# from a GPX file. See docs/BLUEPRINT.md sec 3, sec 15.
#
# The path is stored twice: `geom` (LineString) drives the map and the
# derived length, and `points` (JSON) keeps the full per-point detail
# (elevation, timestamps) for a faithful GPX re-export. Only `geom` +
# metadata ride the sync stream; the raw points are fetched on demand.
# --------------------------------------------------------------------------- #


class GpxTrack(Base, TimestampMixin):
    __tablename__ = "gpx_tracks"
    __table_args__ = (
        CheckConstraint(f"source in ({_TRACK_SOURCES})", name="ck_gpx_track_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    activity: Mapped[str] = mapped_column(String(64), default="mtb", nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), default=TrackSource.recorded.value, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Seconds actually moving/recording (wall time minus pauses); 0 if unknown.
    moving_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    geom: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=False
    )
    # Full fidelity: list of {lat, lon, ele?, t?}. Not queried by element,
    # not serialized into the sync stream.
    points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
