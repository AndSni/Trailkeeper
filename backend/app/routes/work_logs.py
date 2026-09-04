"""Work log CRUD - hours against a task or a trail, logged by hand or
auto-created when a task is marked done (see routes/tasks.py:complete_task).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.models import WorkLog
from app.schemas import WorkLogCreateIn, WorkLogOut, WorkLogUpdateIn

router = APIRouter(prefix="/work-logs", tags=["work-logs"])

DbSession = Annotated[Session, Depends(get_db)]


def _load(db: Session, work_log_id: uuid.UUID) -> WorkLog:
    log = db.get(WorkLog, work_log_id)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work log not found")
    return log


@router.get("", response_model=list[WorkLogOut])
def list_work_logs(
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> list[WorkLog]:
    require_project_member(project_id, membership, user, db)
    return list(
        db.scalars(
            select(WorkLog)
            .where(WorkLog.project_id == project_id)
            .order_by(WorkLog.worked_on.desc(), WorkLog.created_at.desc())
        )
    )


@router.post("", response_model=WorkLogOut, status_code=status.HTTP_201_CREATED)
def create_work_log(
    body: WorkLogCreateIn,
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> WorkLog:
    project = require_project_member(project_id, membership, user, db)
    log = WorkLog(
        organisation_id=project.organisation_id,
        project_id=project.id,
        task_id=body.task_id,
        trail_id=body.trail_id,
        user_id=user.id,
        minutes=body.minutes,
        worked_on=body.worked_on,
        note=body.note,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.patch("/{work_log_id}", response_model=WorkLogOut)
def update_work_log(
    work_log_id: uuid.UUID,
    body: WorkLogUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> WorkLog:
    log = _load(db, work_log_id)
    require_project_member(log.project_id, membership, user, db)
    if log.user_id != user.id and not _is_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own work log")

    if body.minutes is not None:
        log.minutes = body.minutes
    if body.worked_on is not None:
        log.worked_on = body.worked_on
    if body.note is not None:
        log.note = body.note
    db.commit()
    db.refresh(log)
    return log


@router.delete("/{work_log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_log(
    work_log_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    log = _load(db, work_log_id)
    require_project_member(log.project_id, membership, user, db)
    if log.user_id != user.id and not _is_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own work log")
    db.delete(log)
    db.commit()
    return None


def _is_admin(membership) -> bool:
    return is_org_admin(membership)
