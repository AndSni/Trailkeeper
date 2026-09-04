"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import OrgRole, ProjectRole, ProjectStatus, TaskPriority, TaskStatus, TrailStatus

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
