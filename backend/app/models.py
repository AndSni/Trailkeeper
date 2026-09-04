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
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
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


_ORG_ROLES = ", ".join(f"'{r.value}'" for r in OrgRole)
_PROJECT_ROLES = ", ".join(f"'{r.value}'" for r in ProjectRole)
_PROJECT_STATUSES = ", ".join(f"'{s.value}'" for s in ProjectStatus)


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
