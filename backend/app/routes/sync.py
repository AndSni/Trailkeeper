"""The read half of sync (see docs/BLUEPRINT.md sec 8).

`GET /sync/snapshot?project=<id>` - a full bundle for one project, for first
open. `GET /sync/changes?since=<server_seq>` - everything that changed after
that cursor, collapsed to the latest state per entity. The client applies the
snapshot, then polls /changes with the `high_seq` it hands back.

`POST /sync/push` is the write half - see app/sync_push.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, load_visible_project
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.models import (
    ChangeLog,
    JobType,
    Message,
    Project,
    ProjectMember,
    SegmentWorkRecord,
    Task,
    Trail,
    User,
    WorkLog,
)
from app.routes.segment_work import fetch_segment_out
from app.routes.tasks import fetch_task_out
from app.routes.trails import fetch_trail_out
from app.schemas import (
    JobTypeOut,
    MessageOut,
    ProjectMemberOut,
    ProjectOut,
    SyncChangeOut,
    SyncChangesOut,
    SyncPushIn,
    SyncPushOut,
    SyncSnapshotOut,
    WorkLogOut,
)
from app.sync_push import apply_push

router = APIRouter(prefix="/sync", tags=["sync"])

DbSession = Annotated[Session, Depends(get_db)]

_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 500


def _visible_project_ids(db: Session, membership, user) -> set[uuid.UUID]:
    stmt = select(Project.id).where(
        Project.organisation_id == membership.organisation_id, Project.deleted_at.is_(None)
    )
    if not is_org_admin(membership):
        stmt = stmt.join(ProjectMember, ProjectMember.project_id == Project.id).where(
            ProjectMember.user_id == user.id
        )
    return set(db.scalars(stmt))


def _project_members(db: Session, project_id: uuid.UUID) -> list[ProjectMemberOut]:
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.name)
    ).all()
    return [
        ProjectMemberOut(
            user_id=u.id, email=u.email, name=u.name, project_role=pm.project_role
        )
        for pm, u in rows
    ]


def _serialize_entity(db: Session, entity_type: str, entity_id: uuid.UUID) -> dict | list | None:
    """Current JSON-ready state of an entity for a sync `upsert`, or None if
    it's gone (which the caller turns into a `delete` so the client drops
    it). Shape depends on entity_type - see SyncChangeOut.row."""
    if entity_type == "trail":
        out = fetch_trail_out(db, entity_id)
    elif entity_type == "task":
        out = fetch_task_out(db, entity_id)
    elif entity_type == "work_log":
        log = db.get(WorkLog, entity_id)
        out = WorkLogOut.model_validate(log) if log is not None else None
    elif entity_type == "message":
        msg = db.get(Message, entity_id)
        out = None if msg is None or msg.deleted_at is not None else MessageOut.model_validate(msg)
    elif entity_type == "job_type":
        jt = db.get(JobType, entity_id)
        out = None if jt is None or jt.deleted_at is not None else JobTypeOut.model_validate(jt)
    elif entity_type == "segment_work":
        out = fetch_segment_out(db, entity_id)
    elif entity_type == "project":
        project = db.get(Project, entity_id)
        gone = project is None or project.deleted_at is not None
        out = None if gone else ProjectOut.model_validate(project)
    elif entity_type == "project_member":
        # entity_id is the project id; the "row" is that project's member list.
        if db.get(Project, entity_id) is None:
            return None
        return [m.model_dump(mode="json") for m in _project_members(db, entity_id)]
    else:
        return None
    return out.model_dump(mode="json") if out is not None else None


@router.get("/changes", response_model=SyncChangesOut)
def get_changes(
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    since: int = 0,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> SyncChangesOut:
    visible = _visible_project_ids(db, membership, user)

    # Org-wide changes (project_id null - trails) are always visible; project-
    # scoped ones only for projects the caller belongs to.
    scope = ChangeLog.project_id.is_(None)
    if visible:
        scope = scope | ChangeLog.project_id.in_(visible)
    base = select(ChangeLog).where(
        ChangeLog.organisation_id == membership.organisation_id,
        ChangeLog.server_seq > since,
        scope,
    )

    raw = list(db.scalars(base.order_by(ChangeLog.server_seq).limit(limit)))
    if not raw:
        return SyncChangesOut(changes=[], high_seq=since, has_more=False)

    high_seq = raw[-1].server_seq
    has_more = len(raw) == limit

    # Collapse to the latest row per entity within this batch.
    latest: dict[tuple[str, uuid.UUID], ChangeLog] = {}
    for c in raw:
        latest[(c.entity_type, c.entity_id)] = c

    changes: list[SyncChangeOut] = []
    for c in sorted(latest.values(), key=lambda c: c.server_seq):
        row = None if c.op == "delete" else _serialize_entity(db, c.entity_type, c.entity_id)
        changes.append(
            SyncChangeOut(
                server_seq=c.server_seq,
                entity_type=c.entity_type,
                entity_id=c.entity_id,
                project_id=c.project_id,
                op="delete" if (c.op == "delete" or row is None) else "upsert",
                changed_at=c.created_at,
                actor_id=c.actor_id,
                row=row,
            )
        )
    return SyncChangesOut(changes=changes, high_seq=high_seq, has_more=has_more)


@router.post("/push", response_model=SyncPushOut)
def push(
    body: SyncPushIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> SyncPushOut:
    """Apply a batch of offline edits (tasks, work logs). Idempotent per
    `client_op_id`; conflicting ops return the authoritative row unchanged.
    See app/sync_push.py."""
    return apply_push(db, body, membership, user)


@router.get("/snapshot", response_model=SyncSnapshotOut)
def get_snapshot(
    project: uuid.UUID,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> SyncSnapshotOut:
    proj = load_visible_project(project, membership, user, db)

    trail_rows = db.scalars(
        select(Trail.id).where(
            Trail.organisation_id == membership.organisation_id, Trail.deleted_at.is_(None)
        )
    )
    task_rows = db.scalars(
        select(Task.id).where(Task.project_id == proj.id, Task.deleted_at.is_(None))
    )
    work_logs = db.scalars(select(WorkLog).where(WorkLog.project_id == proj.id))
    msgs = db.scalars(
        select(Message)
        .where(Message.project_id == proj.id, Message.deleted_at.is_(None))
        .order_by(Message.created_at)
    )
    job_types = db.scalars(
        select(JobType).where(
            JobType.organisation_id == membership.organisation_id, JobType.deleted_at.is_(None)
        )
    )
    segment_rows = db.scalars(
        select(SegmentWorkRecord.id).where(
            SegmentWorkRecord.project_id == proj.id, SegmentWorkRecord.deleted_at.is_(None)
        )
    )

    high_seq = db.scalar(
        select(func.coalesce(func.max(ChangeLog.server_seq), 0)).where(
            ChangeLog.organisation_id == membership.organisation_id
        )
    )

    return SyncSnapshotOut(
        project=ProjectOut.model_validate(proj),
        members=_project_members(db, proj.id),
        trails=[t for tid in trail_rows if (t := fetch_trail_out(db, tid)) is not None],
        tasks=[t for tid in task_rows if (t := fetch_task_out(db, tid)) is not None],
        work_logs=[WorkLogOut.model_validate(w) for w in work_logs],
        messages=[MessageOut.model_validate(m) for m in msgs],
        job_types=[JobTypeOut.model_validate(j) for j in job_types],
        segment_work=[s for sid in segment_rows if (s := fetch_segment_out(db, sid)) is not None],
        high_seq=high_seq or 0,
    )
