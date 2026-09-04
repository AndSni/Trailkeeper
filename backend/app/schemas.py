"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import OrgRole, ProjectRole, ProjectStatus

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
