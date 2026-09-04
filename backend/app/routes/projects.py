"""Project CRUD and per-project membership.

Visibility: owners and admins see every project in the org; editors and
viewers see only the projects they have been added to. Creating and deleting
projects needs admin+. Editing a project or managing its members needs
admin+ OR being that project's lead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, load_visible_project, require_admin_or_lead
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser, require_org_role
from app.models import Membership, OrgRole, Project, ProjectMember, ProjectRole, ProjectStatus, User
from app.schemas import (
    ProjectCreateIn,
    ProjectMemberIn,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdateIn,
)

router = APIRouter(prefix="/projects", tags=["projects"])

DbSession = Annotated[Session, Depends(get_db)]
AdminMembership = Annotated[Membership, Depends(require_org_role(OrgRole.admin))]


@router.get("", response_model=list[ProjectOut])
def list_projects(
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
) -> list[Project]:
    stmt = select(Project).where(
        Project.organisation_id == membership.organisation_id,
        Project.deleted_at.is_(None),
    )
    if not is_org_admin(membership):
        stmt = stmt.join(ProjectMember, ProjectMember.project_id == Project.id).where(
            ProjectMember.user_id == user.id
        )
    if status_filter is not None:
        stmt = stmt.where(Project.status == status_filter.value)
    return list(db.scalars(stmt.order_by(Project.created_at.desc())))


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreateIn, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> Project:
    project = Project(
        organisation_id=membership.organisation_id,
        name=body.name,
        description=body.description,
        activity=body.activity,
        status=body.status.value,
        created_by_id=user.id,
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id, user_id=user.id, project_role=ProjectRole.lead.value
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> Project:
    return load_visible_project(project_id, membership, user, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> Project:
    project = load_visible_project(project_id, membership, user, db)
    require_admin_or_lead(project, membership, user, db)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.activity is not None:
        project.activity = body.activity
    if body.status is not None:
        project.status = body.status.value
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> None:
    project = load_visible_project(project_id, membership, user, db)
    project.deleted_at = datetime.now(UTC)
    db.commit()
    return None


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_project_members(
    project_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> list[ProjectMemberOut]:
    project = load_visible_project(project_id, membership, user, db)
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id)
        .order_by(User.name)
    ).all()
    return [
        ProjectMemberOut(
            user_id=u.id, email=u.email, name=u.name, project_role=ProjectRole(pm.project_role)
        )
        for pm, u in rows
    ]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: uuid.UUID,
    body: ProjectMemberIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> ProjectMemberOut:
    project = load_visible_project(project_id, membership, user, db)
    require_admin_or_lead(project, membership, user, db)

    target_membership = db.scalar(
        select(Membership).where(
            Membership.organisation_id == membership.organisation_id,
            Membership.user_id == body.user_id,
        )
    )
    if target_membership is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "User is not a member of this organisation"
        )

    existing = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == body.user_id
        )
    )
    if existing is None:
        existing = ProjectMember(
            project_id=project.id, user_id=body.user_id, project_role=body.project_role.value
        )
        db.add(existing)
    else:
        existing.project_role = body.project_role.value
    db.commit()

    target_user = db.get(User, body.user_id)
    return ProjectMemberOut(
        user_id=target_user.id,
        email=target_user.email,
        name=target_user.name,
        project_role=body.project_role,
    )


@router.delete(
    "/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> None:
    project = load_visible_project(project_id, membership, user, db)
    require_admin_or_lead(project, membership, user, db)
    pm = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user_id
        )
    )
    if pm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a project member")
    db.delete(pm)
    db.commit()
    return None
