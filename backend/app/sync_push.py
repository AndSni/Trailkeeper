"""`POST /sync/push` - the offline client's write path (docs/BLUEPRINT.md sec 8).

Phase 1c scope: tasks and work logs (the things a crew edits in the field).
Trails are admin/online-only; task photos get their own binary queue later.

Conflict model (deliberately simple for now): whole-entity last-writer-wins.
Each op carries `base_updated_at` - the row version the client last saw. If
the server row is newer, the op is a **conflict**: the server value stands,
the op is not applied, and the caller gets the authoritative row back to
replace its local copy. Deletes always win. A per-field merge can come later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.config import settings
from app.geo import find_nearest_trail, point_wkt
from app.models import (
    ChangeLog,
    Membership,
    Message,
    ProjectMember,
    PushedOp,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    WorkLog,
)
from app.routes.messages import _fan_out_notifications
from app.routes.tasks import _set_assignees, fetch_task_out, notify_assigned
from app.schemas import MessageOut, SyncOpIn, SyncOpResult, SyncPushIn, SyncPushOut, WorkLogOut
from app.sync import record_change


class _Rejected(Exception):
    pass


class _TaskFields(BaseModel):
    project_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    task_type: str | None = Field(default=None, max_length=64)
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    estimate_min: int | None = Field(default=None, ge=0)
    assignee_ids: list[uuid.UUID] | None = None


class _WorkLogFields(BaseModel):
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    trail_id: uuid.UUID | None = None
    minutes: int | None = Field(default=None, ge=1)
    worked_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)


class _MessageFields(BaseModel):
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    mention_user_ids: list[uuid.UUID] = Field(default_factory=list)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _stale(server_updated_at: datetime, base_updated_at: datetime | None) -> bool:
    """True when the client's edit is based on an older version than the
    server now holds -> the op is a conflict, server value wins."""
    base = _aware(base_updated_at)
    return base is not None and server_updated_at > base


def _task_row(db: Session, task_id: uuid.UUID) -> dict | None:
    out = fetch_task_out(db, task_id)
    return out.model_dump(mode="json") if out is not None else None


def _work_log_row(db: Session, log_id: uuid.UUID) -> dict | None:
    log = db.get(WorkLog, log_id)
    return WorkLogOut.model_validate(log).model_dump(mode="json") if log is not None else None


def _message_row(db: Session, msg_id: uuid.UUID) -> dict | None:
    msg = db.get(Message, msg_id)
    if msg is None or msg.deleted_at is not None:
        return None
    return MessageOut.model_validate(msg).model_dump(mode="json")


def _row_for(db: Session, entity_type: str, entity_id: uuid.UUID) -> dict | None:
    if entity_type == "task":
        return _task_row(db, entity_id)
    if entity_type == "work_log":
        return _work_log_row(db, entity_id)
    if entity_type == "message":
        return _message_row(db, entity_id)
    return None


def _result(op: SyncOpIn, status: str, *, server_seq=None, row=None, message=None) -> SyncOpResult:
    return SyncOpResult(
        client_op_id=op.client_op_id,
        entity_type=op.entity_type,
        entity_id=op.entity_id,
        status=status,
        server_seq=server_seq,
        row=row,
        message=message,
    )


def apply_push(
    db: Session, body: SyncPushIn, membership: Membership, user: User
) -> SyncPushOut:
    results: list[SyncOpResult] = []
    for op in body.ops:
        seen = db.get(PushedOp, op.client_op_id)
        if seen is not None:
            row = _row_for(db, seen.entity_type, seen.entity_id)
            results.append(_result(op, seen.status, row=row))
            continue
        try:
            res = _apply(db, op, membership, user)
        except _Rejected as exc:
            res = _result(op, "rejected", message=str(exc))
        except HTTPException as exc:
            # e.g. require_project_member 404s for a project the caller can't
            # see - reject just this op, not the whole batch.
            res = _result(op, "rejected", message=str(exc.detail))
        db.add(
            PushedOp(
                client_op_id=op.client_op_id,
                organisation_id=membership.organisation_id,
                actor_id=user.id,
                entity_type=op.entity_type,
                entity_id=op.entity_id,
                status=res.status,
            )
        )
        results.append(res)

    db.commit()
    high = db.scalar(
        select(func.coalesce(func.max(ChangeLog.server_seq), 0)).where(
            ChangeLog.organisation_id == membership.organisation_id
        )
    )
    return SyncPushOut(results=results, high_seq=high or 0)


def _apply(db: Session, op: SyncOpIn, membership: Membership, user: User) -> SyncOpResult:
    if op.op not in ("upsert", "delete"):
        raise _Rejected(f"unknown op {op.op!r}")
    if op.entity_type == "task":
        return _apply_task(db, op, membership, user)
    if op.entity_type == "work_log":
        return _apply_work_log(db, op, membership, user)
    if op.entity_type == "message":
        return _apply_message(db, op, membership, user)
    raise _Rejected(f"unsupported entity_type {op.entity_type!r}")


def _apply_task(db: Session, op: SyncOpIn, membership: Membership, user: User) -> SyncOpResult:
    task = db.get(Task, op.entity_id)
    exists = task is not None and task.deleted_at is None
    fields = _TaskFields.model_validate(op.fields)

    if not exists:
        if op.op == "delete":
            return _result(op, "applied", row=None)  # already gone - idempotent
        if fields.project_id is None:
            raise _Rejected("creating a task needs fields.project_id")
        project = require_project_member(fields.project_id, membership, user, db)
    else:
        project = require_project_member(task.project_id, membership, user, db)

    if op.op == "delete":
        task.deleted_at = datetime.now(UTC)
        cl = record_change(
            db, entity_type="task", entity_id=task.id, op="delete",
            organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
        )
        db.flush()
        return _result(op, "applied", server_seq=cl.server_seq, row=None)

    if exists and _stale(task.updated_at, op.base_updated_at):
        return _result(
            op, "conflict", row=_task_row(db, task.id), message="server has a newer version"
        )

    if not exists:
        task = Task(
            id=op.entity_id,
            organisation_id=project.organisation_id,
            project_id=project.id,
            title=fields.title or "Untitled task",
            created_by_id=user.id,
            priority=(fields.priority or TaskPriority.medium).value,
        )
        db.add(task)

    if fields.title is not None:
        task.title = fields.title
    if fields.description is not None:
        task.description = fields.description
    if fields.task_type is not None:
        task.task_type = fields.task_type
    if fields.priority is not None:
        task.priority = fields.priority.value
    if fields.status is not None:
        task.status = fields.status.value
    if fields.estimate_min is not None:
        task.estimate_min = fields.estimate_min
    if fields.lat is not None and fields.lon is not None:
        task.geom = point_wkt(fields.lat, fields.lon)
        nearest = find_nearest_trail(
            db, project.organisation_id, fields.lat, fields.lon, settings.nearest_trail_max_m
        )
        task.nearest_trail_id = nearest[0] if nearest is not None else None

    db.flush()
    if fields.assignee_ids is not None:
        added = _set_assignees(db, task.id, fields.assignee_ids)
        notify_assigned(db, task, added, user.id)
    cl = record_change(
        db, entity_type="task", entity_id=task.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    db.flush()
    return _result(op, "applied", server_seq=cl.server_seq, row=_task_row(db, task.id))


def _apply_work_log(db: Session, op: SyncOpIn, membership: Membership, user: User) -> SyncOpResult:
    log = db.get(WorkLog, op.entity_id)
    fields = _WorkLogFields.model_validate(op.fields)

    if log is None:
        if op.op == "delete":
            return _result(op, "applied", row=None)
        if fields.project_id is None or fields.minutes is None or fields.worked_on is None:
            raise _Rejected("creating a work log needs project_id, minutes and worked_on")
        project = require_project_member(fields.project_id, membership, user, db)
    else:
        project = require_project_member(log.project_id, membership, user, db)
        if log.user_id != user.id and not is_org_admin(membership):
            raise _Rejected("you can only change your own work log")

    if op.op == "delete":
        cl = record_change(
            db, entity_type="work_log", entity_id=op.entity_id, op="delete",
            organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
        )
        db.delete(log)
        db.flush()
        return _result(op, "applied", server_seq=cl.server_seq, row=None)

    if log is not None and _stale(log.updated_at, op.base_updated_at):
        return _result(
            op, "conflict", row=_work_log_row(db, log.id), message="server has a newer version"
        )

    if log is None:
        log = WorkLog(
            id=op.entity_id,
            organisation_id=project.organisation_id,
            project_id=project.id,
            task_id=fields.task_id,
            trail_id=fields.trail_id,
            user_id=user.id,
            minutes=fields.minutes,
            worked_on=fields.worked_on,
            note=fields.note or "",
        )
        db.add(log)
    else:
        if fields.minutes is not None:
            log.minutes = fields.minutes
        if fields.worked_on is not None:
            log.worked_on = fields.worked_on
        if fields.note is not None:
            log.note = fields.note

    db.flush()
    cl = record_change(
        db, entity_type="work_log", entity_id=log.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    db.flush()
    return _result(op, "applied", server_seq=cl.server_seq, row=_work_log_row(db, log.id))


def _apply_message(db: Session, op: SyncOpIn, membership: Membership, user: User) -> SyncOpResult:
    msg = db.get(Message, op.entity_id)

    if op.op == "delete":
        if msg is None or msg.deleted_at is not None:
            return _result(op, "applied", row=None)
        require_project_member(msg.project_id, membership, user, db)
        if msg.author_id != user.id and not is_org_admin(membership):
            raise _Rejected("only the author or an admin can delete a message")
        msg.deleted_at = datetime.now(UTC)
        cl = record_change(
            db, entity_type="message", entity_id=msg.id, op="delete",
            organisation_id=msg.organisation_id, project_id=msg.project_id, actor_id=user.id,
        )
        db.flush()
        return _result(op, "applied", server_seq=cl.server_seq, row=None)

    # upsert == create; messages are never edited, so an existing id is a no-op
    if msg is not None:
        return _result(op, "applied", row=_message_row(db, msg.id))

    fields = _MessageFields.model_validate(op.fields)
    if fields.project_id is None or not fields.body:
        raise _Rejected("creating a message needs project_id and body")
    project = require_project_member(fields.project_id, membership, user, db)

    task = None
    if fields.task_id is not None:
        task = db.get(Task, fields.task_id)
        if task is None or task.project_id != project.id or task.deleted_at is not None:
            raise _Rejected("task not found in this project")

    member_ids = set(
        db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project.id))
    )
    mentioned = [uid for uid in dict.fromkeys(fields.mention_user_ids) if uid in member_ids]

    msg = Message(
        id=op.entity_id,
        organisation_id=project.organisation_id,
        project_id=project.id,
        task_id=fields.task_id,
        author_id=user.id,
        body=fields.body,
        mentioned_user_ids=[str(uid) for uid in mentioned],
    )
    db.add(msg)
    db.flush()
    cl = record_change(
        db, entity_type="message", entity_id=msg.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    _fan_out_notifications(
        db, msg, project.organisation_id, task, member_ids, set(mentioned), user
    )
    db.flush()
    return _result(op, "applied", server_seq=cl.server_seq, row=_message_row(db, msg.id))
