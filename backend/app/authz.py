"""Shared project-visibility and role checks - used by routes/projects.py and
every route scoped to a project (tasks, work logs, ...). See
docs/BLUEPRINT.md sec 13 for the permissions matrix this implements.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Membership, OrgRole, Project, ProjectMember, ProjectRole, User


def is_org_admin(membership: Membership) -> bool:
    return OrgRole(membership.org_role) in (OrgRole.owner, OrgRole.admin)


def load_visible_project(
    project_id: uuid.UUID, membership: Membership, user: User, db: Session
) -> Project:
    """404s (not 403) for a project the caller can't see, org admins see
    every project in their org; everyone else only ones they're a member of.
    """
    project = db.get(Project, project_id)
    if (
        project is None
        or project.organisation_id != membership.organisation_id
        or project.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if is_org_admin(membership):
        return project
    is_member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    if is_member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def require_project_member(
    project_id: uuid.UUID, membership: Membership, user: User, db: Session
) -> Project:
    """Like load_visible_project, but any project member (not just admin/
    lead) may write - used for tasks, work logs, comments: rank-and-file
    crew members log real work, only project structure needs admin/lead."""
    return load_visible_project(project_id, membership, user, db)


def require_admin_or_lead(
    project: Project, membership: Membership, user: User, db: Session
) -> None:
    if is_org_admin(membership):
        return
    pm = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    if pm is None or ProjectRole(pm.project_role) is not ProjectRole.lead:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires org admin or project lead")
