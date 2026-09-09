"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import (
    InspectionRisk,
    OrgRole,
    ProjectRole,
    ProjectStatus,
    StructureStatus,
    StructureType,
    TaskPriority,
    TaskStatus,
    TrailStatus,
)

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    organisation_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AcceptInviteIn(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


# --------------------------------------------------------------------------- #
# Users / memberships
# --------------------------------------------------------------------------- #


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organisation_id: uuid.UUID
    org_role: OrgRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    is_active: bool


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


class OrgMemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: str
    org_role: OrgRole


class MemberRoleIn(BaseModel):
    org_role: OrgRole


# --------------------------------------------------------------------------- #
# Organisation
# --------------------------------------------------------------------------- #


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    timezone: str


class OrgUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class InviteIn(BaseModel):
    email: EmailStr
    org_role: OrgRole = OrgRole.editor


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    org_role: OrgRole
    token: str
    expires_at: datetime
    accepted_at: datetime | None


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #


class ProjectCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    activity: str = Field(default="mtb", max_length=64)
    status: ProjectStatus = ProjectStatus.planning


class ProjectUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    activity: str | None = Field(default=None, max_length=64)
    status: ProjectStatus | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    description: str
    activity: str
    status: ProjectStatus
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectMemberIn(BaseModel):
    user_id: uuid.UUID
    project_role: ProjectRole = ProjectRole.member


class ProjectMemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: str
    project_role: ProjectRole


# --------------------------------------------------------------------------- #
# Trails
# --------------------------------------------------------------------------- #


class TrailCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    activity: str = Field(default="mtb", max_length=64)
    difficulty: str = Field(default="", max_length=32)
    status: TrailStatus = TrailStatus.open
    # (lat, lon) pairs in order along the line - at least 2.
    points: list[tuple[float, float]] = Field(min_length=2)


class TrailUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    difficulty: str | None = Field(default=None, max_length=32)
    status: TrailStatus | None = None


class TrailOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    activity: str
    difficulty: str
    status: TrailStatus
    source: str
    length_m: float
    geometry: dict
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    task_type: str = Field(default="", max_length=64)
    priority: TaskPriority = TaskPriority.medium
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    estimate_min: int | None = Field(default=None, ge=0)
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("lon")
    @classmethod
    def _both_or_neither(cls, lon: float | None, info) -> float | None:
        lat = info.data.get("lat")
        if (lat is None) != (lon is None):
            raise ValueError("lat and lon must be given together")
        return lon


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    task_type: str | None = Field(default=None, max_length=64)
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    estimate_min: int | None = Field(default=None, ge=0)


class TaskAssigneesIn(BaseModel):
    user_ids: list[uuid.UUID]


class TaskCompleteIn(BaseModel):
    # Overrides the estimate for the auto work log; omit to use the task's
    # estimate_min (or skip logging entirely if that's also unset).
    minutes: int | None = Field(default=None, ge=0)


class TaskPhotoOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    caption: str
    uploaded_by_id: uuid.UUID | None
    created_at: datetime
    url: str


class TaskOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    task_type: str
    priority: TaskPriority
    status: TaskStatus
    geometry: dict | None
    nearest_trail_id: uuid.UUID | None
    estimate_min: int | None
    created_by_id: uuid.UUID | None
    assignee_ids: list[uuid.UUID]
    photos: list[TaskPhotoOut]
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Work logs
# --------------------------------------------------------------------------- #


class WorkLogCreateIn(BaseModel):
    task_id: uuid.UUID | None = None
    trail_id: uuid.UUID | None = None
    minutes: int = Field(ge=1)
    worked_on: date
    note: str = Field(default="", max_length=1000)


class WorkLogUpdateIn(BaseModel):
    minutes: int | None = Field(default=None, ge=1)
    worked_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)


class WorkLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    trail_id: uuid.UUID | None
    user_id: uuid.UUID
    minutes: int
    worked_on: date
    note: str
    auto_from_task: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Messages / discussion
# --------------------------------------------------------------------------- #


class MessageCreateIn(BaseModel):
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None  # null = the project's own thread
    body: str = Field(min_length=1, max_length=8000)
    mention_user_ids: list[uuid.UUID] = Field(default_factory=list)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    author_id: uuid.UUID | None
    body: str
    mentioned_user_ids: list[uuid.UUID]
    created_at: datetime



# --------------------------------------------------------------------------- #
# Segment timing (Phase 4)
# --------------------------------------------------------------------------- #


class JobTypeCreateIn(BaseModel):
    activity: str = Field(default="mtb", max_length=64)
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    unit: str  # hours | km | m2 | count
    default_crew: int = Field(default=1, ge=1)
    expected_rate: float | None = Field(default=None, ge=0)  # minutes per unit
    color: str = Field(default="", max_length=16)
    sort_group: str = Field(default="", max_length=64)


class JobTypeUpdateIn(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = None
    default_crew: int | None = Field(default=None, ge=1)
    expected_rate: float | None = Field(default=None, ge=0)
    color: str | None = Field(default=None, max_length=16)
    sort_group: str | None = Field(default=None, max_length=64)


class JobTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    activity: str
    key: str
    label: str
    unit: str
    default_crew: int
    expected_rate: float | None
    color: str
    sort_group: str
    created_at: datetime
    updated_at: datetime


class SegmentWorkCreateIn(BaseModel):
    project_id: uuid.UUID
    job_type_id: uuid.UUID
    trail_id: uuid.UUID | None = None
    geometry: dict | None = None  # GeoJSON geometry (LineString / Polygon / Point)
    quantity: float | None = Field(default=None, ge=0)
    quantity_source: str = "manual"  # measured | manual
    started_at: datetime
    ended_at: datetime | None = None
    active_seconds: int = Field(default=0, ge=0)
    pauses: list = Field(default_factory=list)
    crew_size: int = Field(default=1, ge=1)
    equipment: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)


class SegmentWorkUpdateIn(BaseModel):
    job_type_id: uuid.UUID | None = None
    trail_id: uuid.UUID | None = None
    geometry: dict | None = None
    quantity: float | None = Field(default=None, ge=0)
    quantity_source: str | None = None
    ended_at: datetime | None = None
    active_seconds: int | None = Field(default=None, ge=0)
    pauses: list | None = None
    crew_size: int | None = Field(default=None, ge=1)
    equipment: list[str] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class SegmentWorkOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    job_type_id: uuid.UUID | None
    trail_id: uuid.UUID | None
    geometry: dict | None
    quantity: float
    unit: str
    quantity_source: str
    started_at: datetime
    ended_at: datetime | None
    active_seconds: int
    pauses: list
    crew_size: int
    equipment: list[str]
    notes: str
    created_by_id: uuid.UUID | None
    # Derived - never stored (docs/BLUEPRINT.md sec 10).
    person_hours: float
    rate_min_per_unit: float | None
    throughput_per_hour: float | None
    vs_expected_min_per_unit: float | None
    created_at: datetime
    updated_at: datetime


class SegmentRollupGroup(BaseModel):
    group_key: str
    group_label: str
    record_count: int
    unit: str
    total_quantity: float
    total_person_hours: float
    mean_rate_min_per_unit: float | None  # weighted: total minutes / total quantity
    expected_rate: float | None
    delta_min_per_unit: float | None


class SegmentRollupOut(BaseModel):
    group_by: str
    groups: list[SegmentRollupGroup]


# --------------------------------------------------------------------------- #
# Structures & inspections (Phase 5)
# --------------------------------------------------------------------------- #


class StructureCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    structure_type: StructureType = StructureType.other
    status: StructureStatus = StructureStatus.good
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    material: str = Field(default="", max_length=64)
    color: str = Field(default="", max_length=16)
    installed_on: date | None = None
    inspection_interval_days: int | None = Field(default=None, ge=1)
    notes: str = Field(default="", max_length=4000)

    @field_validator("lon")
    @classmethod
    def _both_or_neither(cls, lon: float | None, info) -> float | None:
        lat = info.data.get("lat")
        if (lat is None) != (lon is None):
            raise ValueError("lat and lon must be given together")
        return lon


class StructureUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    structure_type: StructureType | None = None
    status: StructureStatus | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    material: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    installed_on: date | None = None
    inspection_interval_days: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=4000)


class StructureOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    structure_type: StructureType
    status: StructureStatus
    geometry: dict | None
    nearest_trail_id: uuid.UUID | None
    material: str
    color: str
    installed_on: date | None
    inspection_interval_days: int | None
    notes: str
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InspectionFormCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_type: str = Field(default="", max_length=32)
    # Field defs: {key, label, type, required?, choices?, help?}. `type` is
    # one of models.INSPECTION_FIELD_TYPES. Validated in the route.
    fields: list[dict] = Field(default_factory=list)
    is_active: bool = True


class InspectionFormUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_type: str | None = Field(default=None, max_length=32)
    fields: list[dict] | None = None
    is_active: bool | None = None


class InspectionFormOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    target_type: str
    fields: list[dict]
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InspectionCreateIn(BaseModel):
    project_id: uuid.UUID
    structure_id: uuid.UUID
    form_id: uuid.UUID | None = None
    inspected_on: date | None = None
    answers: dict = Field(default_factory=dict)
    risk: InspectionRisk | None = None
    condition: StructureStatus | None = None
    notes: str = Field(default="", max_length=4000)


class InspectionUpdateIn(BaseModel):
    inspected_on: date | None = None
    answers: dict | None = None
    risk: InspectionRisk | None = None
    condition: StructureStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class InspectionOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    structure_id: uuid.UUID
    form_id: uuid.UUID | None
    form_version: int | None
    inspector_id: uuid.UUID | None
    inspected_on: date
    answers: dict
    risk: InspectionRisk | None
    condition: StructureStatus | None
    notes: str
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# GPX tracks (Phase 3)
# --------------------------------------------------------------------------- #


class TrackPointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    ele: float | None = None
    t: datetime | None = None  # per-point timestamp


class TrackCreateIn(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    activity: str = Field(default="mtb", max_length=64)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    moving_seconds: int = Field(default=0, ge=0)
    points: list[TrackPointIn] = Field(min_length=2)


class TrackUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    activity: str | None = Field(default=None, max_length=64)


class TrackOut(BaseModel):
    """Metadata + geometry for the sync stream and list views - never the
    raw `points` (fetch those via GET /tracks/{id}/gpx)."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    activity: str
    source: str
    started_at: datetime | None
    ended_at: datetime | None
    moving_seconds: int
    length_m: float
    point_count: int
    geometry: dict
    recorded_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #


class SyncChangeOut(BaseModel):
    server_seq: int
    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    op: str  # "upsert" | "delete"
    changed_at: datetime
    actor_id: uuid.UUID | None
    # The entity's current serialized form for an upsert; null for a delete.
    # Shape depends on entity_type (a TrailOut, TaskOut, WorkLogOut,
    # ProjectOut, or - for project_member - a list of ProjectMemberOut).
    row: dict | list | None


class SyncChangesOut(BaseModel):
    changes: list[SyncChangeOut]
    high_seq: int
    has_more: bool


class SyncSnapshotOut(BaseModel):
    project: ProjectOut
    members: list[ProjectMemberOut]
    trails: list[TrailOut]
    tasks: list[TaskOut]
    work_logs: list[WorkLogOut]
    messages: list[MessageOut] = []
    job_types: list[JobTypeOut] = []
    segment_work: list[SegmentWorkOut] = []
    structures: list[StructureOut] = []
    inspection_forms: list[InspectionFormOut] = []
    inspections: list[InspectionOut] = []
    tracks: list[TrackOut] = []
    high_seq: int


class SyncOpIn(BaseModel):
    client_op_id: uuid.UUID  # client-generated idempotency key, one per op
    entity_type: str  # "task" | "work_log"
    entity_id: uuid.UUID  # client-minted for a create
    op: str  # "upsert" | "delete"
    # The updated_at the client last saw; null for a create. If the server
    # row is newer, the op is a conflict and the server value wins.
    base_updated_at: datetime | None = None
    fields: dict = Field(default_factory=dict)


class SyncPushIn(BaseModel):
    ops: list[SyncOpIn] = Field(max_length=200)


class SyncOpResult(BaseModel):
    client_op_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    status: str  # "applied" | "conflict" | "rejected"
    server_seq: int | None = None
    row: dict | None = None  # the entity's authoritative current state
    message: str | None = None


class SyncPushOut(BaseModel):
    results: list[SyncOpResult]
    high_seq: int


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    subject_type: str
    subject_id: uuid.UUID
    project_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationReadIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)
    all: bool = False


class DeviceRegisterIn(BaseModel):
    fcm_token: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="android", max_length=16)
    app_version: str = Field(default="", max_length=32)
